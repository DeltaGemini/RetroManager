package com.retromanager.phone;

import android.os.Handler;
import android.os.Looper;
import android.view.InputDevice;
import android.view.KeyEvent;
import android.view.MotionEvent;

/** A controller on the app's page. A page inside the app isn't given a controller's presses, so
 *  they're passed to it (RMPad, in the Console): the D-pad or stick chooses, A opens or plays,
 *  B goes back, X is the game's page, L1 and R1 a page up and down. A stick held over carries on. */
final class Pad {
    private final MainActivity app;
    private final Handler repeat = new Handler(Looper.getMainLooper());
    private String stick;
    private final Runnable stickAgain = new Runnable() {
        @Override public void run() {
            if (stick == null) return;
            send(stick);
            repeat.postDelayed(this, 110);
        }
    };

    Pad(MainActivity app) { this.app = app; }

    private static String keyFor(int code) {
        switch (code) {
            case KeyEvent.KEYCODE_DPAD_UP: return "ArrowUp";
            case KeyEvent.KEYCODE_DPAD_DOWN: return "ArrowDown";
            case KeyEvent.KEYCODE_DPAD_LEFT: return "ArrowLeft";
            case KeyEvent.KEYCODE_DPAD_RIGHT: return "ArrowRight";
            case KeyEvent.KEYCODE_DPAD_CENTER:
            case KeyEvent.KEYCODE_BUTTON_A:
            case KeyEvent.KEYCODE_BUTTON_START: return "Enter";
            case KeyEvent.KEYCODE_BUTTON_B: return "Escape";
            case KeyEvent.KEYCODE_BUTTON_X: return "e";
            case KeyEvent.KEYCODE_BUTTON_L1: return "PageUp";
            case KeyEvent.KEYCODE_BUTTON_R1: return "PageDown";
            default: return null;
        }
    }

    private static boolean fromPad(int source) {
        return (source & InputDevice.SOURCE_GAMEPAD) == InputDevice.SOURCE_GAMEPAD
                || (source & InputDevice.SOURCE_JOYSTICK) == InputDevice.SOURCE_JOYSTICK
                || (source & InputDevice.SOURCE_DPAD) == InputDevice.SOURCE_DPAD;
    }

    private void send(String key) {
        if (!app.isFinishing() && !app.isDestroyed()) app.web.evaluateJavascript("window.RMPad&&window.RMPad('" + key + "')", null);
    }

    /** A button: whether it was the controller's, and passed to the page. */
    boolean key(KeyEvent event) {
        String key = fromPad(event.getSource()) ? keyFor(event.getKeyCode()) : null;
        if (key == null) return false;
        // (held down, only the ones that move carry on)
        if (event.getAction() == KeyEvent.ACTION_DOWN && (event.getRepeatCount() == 0 || key.startsWith("Arrow") || key.startsWith("Page"))) send(key);
        return true;
    }

    /** The D-pad as a "hat", or the left stick: whether it was, and passed to the page. */
    boolean motion(MotionEvent event) {
        if ((event.getSource() & InputDevice.SOURCE_JOYSTICK) != InputDevice.SOURCE_JOYSTICK
                || event.getAction() != MotionEvent.ACTION_MOVE) return false;
        String now = Decide.stickKey(event.getAxisValue(MotionEvent.AXIS_HAT_X), event.getAxisValue(MotionEvent.AXIS_HAT_Y),
                event.getAxisValue(MotionEvent.AXIS_X), event.getAxisValue(MotionEvent.AXIS_Y));
        if (now == null ? stick != null : !now.equals(stick)) {
            stick = now;
            repeat.removeCallbacks(stickAgain);
            if (now != null) {
                send(now);
                repeat.postDelayed(stickAgain, 380);
            }
        }
        return true;
    }

    /** The app is going: a stick held stops carrying on. */
    void stop() {
        stick = null;
        repeat.removeCallbacks(stickAgain);
    }
}
