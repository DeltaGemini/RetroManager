package com.retromanager.phone;

import android.content.ContentResolver;
import android.content.Context;
import android.database.Cursor;
import android.net.Uri;
import android.os.Environment;
import android.provider.DocumentsContract;
import android.provider.DocumentsContract.Document;

import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.List;

/**
 * The RetroArch folder the person chose, which the app may read and write
 * through Android's folder picker (no "all files" permission). Files are named
 * by their path inside it ("roms/snes/Game.sfc"). RetroArch is handed real
 * paths, so the folder has to be on the phone's own storage or its SD card,
 * where a picked folder's id is "<volume>:<path>".
 */
final class Folder {
    static final String STORAGE = "com.android.externalstorage.documents";
    private static final String[] COLUMNS = {Document.COLUMN_DISPLAY_NAME, Document.COLUMN_SIZE, Document.COLUMN_LAST_MODIFIED, Document.COLUMN_MIME_TYPE};

    static final class Entry {
        String name;
        long size, modified;
        boolean folder;
    }

    private final ContentResolver resolver;
    private final Uri tree;
    private final String rootId;

    Folder(Context context, Uri tree) {
        this.resolver = context.getContentResolver();
        this.tree = tree;
        this.rootId = DocumentsContract.getTreeDocumentId(tree);
    }

    /** Whether a picked folder is one RetroArch can be given paths in. */
    static boolean usable(Uri tree) {
        try {
            return tree != null && STORAGE.equals(tree.getAuthority()) && DocumentsContract.getTreeDocumentId(tree).indexOf(':') > 0;
        } catch (IllegalArgumentException e) {
            return false;
        }
    }

    /** The folder's path on the phone ("/storage/emulated/0/RetroArch"). */
    String path() {
        int colon = rootId.indexOf(':');
        String volume = rootId.substring(0, colon), inside = rootId.substring(colon + 1);
        String base = "primary".equalsIgnoreCase(volume) ? Environment.getExternalStorageDirectory().getAbsolutePath() : "/storage/" + volume;
        return inside.isEmpty() ? base : base + "/" + inside;
    }

    String path(String rel) {
        String clean = clean(rel);
        return clean.isEmpty() ? path() : path() + "/" + clean;
    }

    /** A path as it's kept on the phone: no "." or ".." parts, and none of the
     *  characters the phone's storage won't take in a name (it would swap them itself). */
    static String clean(String rel) {
        StringBuilder out = new StringBuilder();
        for (String part : rel.replace('\\', '/').split("/")) {
            if (part.isEmpty() || part.equals(".") || part.equals("..")) continue;
            if (out.length() > 0) out.append('/');
            for (int i = 0; i < part.length(); i++) {
                char c = part.charAt(i);
                out.append(c < 0x20 || c == 0x7f || "\"*:<>?|".indexOf(c) >= 0 ? '_' : c);
            }
        }
        return out.toString();
    }

    private String id(String rel) {
        String clean = clean(rel);
        return clean.isEmpty() ? rootId : rootId.endsWith(":") ? rootId + clean : rootId + "/" + clean;
    }

    /** A file as a document another app can be handed (and allowed to read). */
    Uri document(String rel) {
        return uri(rel);
    }

    private Uri uri(String rel) {
        return DocumentsContract.buildDocumentUriUsingTree(tree, id(rel));
    }

    private static Entry entry(Cursor cursor) {
        Entry entry = new Entry();
        entry.name = cursor.getString(0);
        entry.size = cursor.isNull(1) ? 0 : cursor.getLong(1);
        entry.modified = cursor.isNull(2) ? 0 : cursor.getLong(2);
        entry.folder = Document.MIME_TYPE_DIR.equals(cursor.getString(3));
        return entry;
    }

    /** The file or folder at a path, or null if there's none. */
    Entry stat(String rel) {
        try (Cursor cursor = resolver.query(uri(rel), COLUMNS, null, null, null)) {
            return cursor != null && cursor.moveToFirst() ? entry(cursor) : null;
        } catch (Exception e) {
            // (the storage provider throws for a path that isn't there)
            return null;
        }
    }

    /** What's directly inside a folder (empty if it isn't one). */
    List<Entry> list(String rel) {
        List<Entry> entries = new ArrayList<>();
        try (Cursor cursor = resolver.query(DocumentsContract.buildChildDocumentsUriUsingTree(tree, id(rel)), COLUMNS, null, null, null)) {
            while (cursor != null && cursor.moveToNext()) entries.add(entry(cursor));
        } catch (Exception e) {
            // not there, or not a folder
        }
        return entries;
    }

    /** Makes a folder, and the ones above it, if they aren't there. */
    boolean folders(String rel) {
        String path = "";
        for (String part : clean(rel).split("/")) {
            if (part.isEmpty()) continue;
            String parent = path;
            path = path.isEmpty() ? part : path + "/" + part;
            if (stat(path) != null) continue;
            try {
                if (DocumentsContract.createDocument(resolver, uri(parent), Document.MIME_TYPE_DIR, part) == null) return false;
            } catch (Exception e) {
                return false;
            }
        }
        return true;
    }

    InputStream read(String rel) throws IOException {
        try {
            InputStream in = resolver.openInputStream(uri(rel));
            if (in == null) throw new FileNotFoundException(rel);
            return in;
        } catch (SecurityException | IllegalArgumentException e) {
            throw new FileNotFoundException(rel);
        }
    }

    /** Opens a file for writing from its start, making it (and its folders) if need be. */
    OutputStream write(String rel) throws IOException {
        String clean = clean(rel);
        int slash = clean.lastIndexOf('/');
        String parent = slash < 0 ? "" : clean.substring(0, slash), name = clean.substring(slash + 1);
        try {
            Uri target = uri(clean);
            if (stat(clean) == null) {
                if (!folders(parent)) throw new IOException("Couldn't make the folder " + parent);
                Uri made = DocumentsContract.createDocument(resolver, uri(parent), "application/octet-stream", name);
                if (made == null) throw new IOException("Couldn't make " + clean);
                if (!DocumentsContract.getDocumentId(made).equals(id(clean))) {
                    // The phone gave it another name: RetroArch wouldn't find it under ours
                    DocumentsContract.deleteDocument(resolver, made);
                    throw new IOException("The phone can't keep a file called " + name);
                }
            }
            OutputStream out = resolver.openOutputStream(target, "wt");
            if (out == null) throw new IOException("Couldn't open " + clean);
            return out;
        } catch (SecurityException | IllegalArgumentException | IllegalStateException e) {
            throw new IOException("Couldn't write " + clean + ": " + e.getMessage());
        }
    }

    /** Opens a file that's there to add to its end. */
    OutputStream append(String rel) throws IOException {
        try {
            OutputStream out = resolver.openOutputStream(uri(rel), "wa");
            if (out == null) throw new IOException("Couldn't open " + rel);
            return out;
        } catch (SecurityException | IllegalArgumentException | IllegalStateException e) {
            throw new IOException("Couldn't add to " + rel + ": " + e.getMessage());
        }
    }

    boolean delete(String rel) {
        try {
            return DocumentsContract.deleteDocument(resolver, uri(rel));
        } catch (Exception e) {
            return false;
        }
    }

    /** Renames a file where it is, replacing one already called that. */
    boolean rename(String rel, String name) {
        String clean = clean(rel);
        int slash = clean.lastIndexOf('/');
        String target = (slash < 0 ? "" : clean.substring(0, slash + 1)) + clean(name);
        if (stat(target) != null) delete(target);
        try {
            return DocumentsContract.renameDocument(resolver, uri(clean), clean(name)) != null;
        } catch (Exception e) {
            return false;
        }
    }
}
