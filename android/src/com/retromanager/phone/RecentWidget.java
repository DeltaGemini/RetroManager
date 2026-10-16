package com.retromanager.phone;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.view.View;
import android.widget.RemoteViews;

import org.json.JSONArray;
import org.json.JSONObject;

/** The home screen widget: the games played most recently (Recent), each a
 *  picture and its name that starts it; the heading opens the app. Asks for
 *  the list again when Android updates it (every hour or so) as well as when
 *  the app opens and after a game. */
public class RecentWidget extends AppWidgetProvider {
    private static final int[] SLOTS = {R.id.slot0, R.id.slot1, R.id.slot2, R.id.slot3, R.id.slot4};
    private static final int[] ART = {R.id.art0, R.id.art1, R.id.art2, R.id.art3, R.id.art4};
    private static final int[] NAMES = {R.id.name0, R.id.name1, R.id.name2, R.id.name3, R.id.name4};

    @Override public void onUpdate(Context context, AppWidgetManager widgets, int[] ids) {
        draw(context, widgets, ids);
        // (then the list again from RetroManager, which redraws them)
        PendingResult pending = goAsync();
        new Thread(() -> {
            try {
                Recent.refresh(context);
            } finally {
                pending.finish();
            }
        }).start();
    }

    static void draw(Context context, AppWidgetManager widgets, int[] ids) {
        JSONArray games = Recent.kept(context);
        RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.widget_recent);
        PendingIntent open = PendingIntent.getActivity(context, 100,
                new Intent(context, MainActivity.class).setAction(Intent.ACTION_MAIN).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        views.setOnClickPendingIntent(R.id.heading, open);
        views.setViewVisibility(R.id.empty, games.length() == 0 ? View.VISIBLE : View.GONE);
        views.setOnClickPendingIntent(R.id.empty, open);
        for (int i = 0; i < SLOTS.length; i++) {
            JSONObject game = games.optJSONObject(i);
            if (game == null) {
                views.setViewVisibility(SLOTS[i], View.GONE);
                continue;
            }
            views.setViewVisibility(SLOTS[i], View.VISIBLE);
            views.setTextViewText(NAMES[i], game.optString("name"));
            Bitmap art = Recent.picture(context, i);
            if (art != null) views.setImageViewBitmap(ART[i], art);
            else views.setImageViewResource(ART[i], R.drawable.widget_no_art);
            Intent play = Recent.play(context, game.optString("system"), game.optString("rom"));
            views.setOnClickPendingIntent(SLOTS[i], PendingIntent.getActivity(context, i, play,
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE));
        }
        widgets.updateAppWidget(ids, views);
    }
}
