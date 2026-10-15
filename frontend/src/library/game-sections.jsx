// Small helpers the library page's panels share.
// Part of the library page (index.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define.

const formatBytes = (n) => n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : n < 1073741824 ? `${(n / 1048576).toFixed(1)} MB` : `${(n / 1073741824).toFixed(2)} GB`;
