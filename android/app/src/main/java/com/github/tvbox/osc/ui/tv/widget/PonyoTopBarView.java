package com.github.tvbox.osc.ui.tv.widget;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Rect;
import android.os.Handler;
import android.os.Looper;
import android.util.AttributeSet;
import android.view.View;

import androidx.annotation.Nullable;

import com.github.tvbox.osc.R;

/** 顶栏专用的遥控器反馈动画，使用 8 列、15 行轻量图集。 */
public class PonyoTopBarView extends View {
    public enum State {
        IDLE(0, 6, 280L),
        DPAD_RIGHT(1, 8, 110L),
        DPAD_LEFT(2, 8, 110L),
        SUCCESS(3, 4, 160L),
        DPAD_UP(4, 5, 130L),
        FAILED(5, 8, 210L),
        WAITING(6, 6, 240L),
        BUSY(7, 6, 180L),
        REVIEW(8, 6, 210L),
        DPAD_DOWN(9, 5, 130L),
        CONFIRM(10, 4, 140L),
        BACK(11, 5, 150L),
        MENU(12, 5, 160L),
        BLOCKED(13, 4, 150L),
        SETTINGS(14, 6, 180L);

        final int row;
        final int frames;
        final long frameDelayMs;

        State(int row, int frames, long frameDelayMs) {
            this.row = row;
            this.frames = frames;
            this.frameDelayMs = frameDelayMs;
        }
    }

    private static final int COLUMNS = 8;
    private static final int ROWS = 15;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Rect source = new Rect();
    private final Rect destination = new Rect();
    private Bitmap atlas;
    private State state = State.IDLE;
    private State baseState = State.IDLE;
    private State heldDirection;
    private int frame;
    private boolean oneShot;
    private boolean reduceMotion;
    private boolean running;

    private final Runnable tick = new Runnable() {
        @Override
        public void run() {
            if (!running) return;
            if (!reduceMotion) {
                frame++;
                if (frame >= frameCount(state)) {
                    frame = 0;
                    if (oneShot) {
                        state = baseState;
                        oneShot = false;
                    }
                }
                invalidate();
            }
            handler.postDelayed(this, reduceMotion ? 500L : state.frameDelayMs);
        }
    };

    public PonyoTopBarView(Context context) {
        this(context, null);
    }

    public PonyoTopBarView(Context context, @Nullable AttributeSet attrs) {
        this(context, attrs, 0);
    }

    public PonyoTopBarView(Context context, @Nullable AttributeSet attrs, int defStyleAttr) {
        super(context, attrs, defStyleAttr);
        paint.setFilterBitmap(true);
        atlas = BitmapFactory.decodeResource(getResources(), R.drawable.ponyo_remote_spritesheet);
        setLayerType(View.LAYER_TYPE_SOFTWARE, null);
    }

    public void setBaseState(State newBaseState) {
        if (newBaseState == null) return;
        baseState = newBaseState;
        if (!oneShot && heldDirection == null) {
            setDisplayedState(newBaseState);
        }
    }

    public State getBaseState() {
        return baseState;
    }

    public void playOnce(State temporaryState) {
        if (temporaryState == null || heldDirection != null) return;
        state = temporaryState;
        frame = 0;
        oneShot = !reduceMotion;
        invalidate();
        if (reduceMotion) {
            handler.removeCallbacks(returnToBase);
            handler.postDelayed(returnToBase, 120L);
        }
    }

    public void startHeldDirection(State direction) {
        if (direction != State.DPAD_LEFT && direction != State.DPAD_RIGHT) return;
        handler.removeCallbacks(returnToBase);
        if (heldDirection == direction) return;
        heldDirection = direction;
        state = direction;
        frame = 0;
        oneShot = false;
        invalidate();
    }

    public void stopHeldDirection() {
        if (heldDirection == null) return;
        heldDirection = null;
        oneShot = !reduceMotion;
        if (reduceMotion) {
            handler.removeCallbacks(returnToBase);
            handler.postDelayed(returnToBase, 120L);
        }
    }

    public void setReduceMotion(boolean reduceMotion) {
        this.reduceMotion = reduceMotion;
        frame = 0;
        invalidate();
    }

    private final Runnable returnToBase = new Runnable() {
        @Override
        public void run() {
            if (heldDirection == null) {
                oneShot = false;
                setDisplayedState(baseState);
            }
        }
    };

    private void setDisplayedState(State newState) {
        state = newState;
        frame = 0;
        invalidate();
    }

    private int frameCount(State value) {
        return Math.max(1, Math.min(COLUMNS, value.frames));
    }

    @Override
    protected void onAttachedToWindow() {
        super.onAttachedToWindow();
        running = true;
        handler.removeCallbacks(tick);
        handler.post(tick);
    }

    @Override
    protected void onDetachedFromWindow() {
        running = false;
        handler.removeCallbacks(tick);
        handler.removeCallbacks(returnToBase);
        super.onDetachedFromWindow();
    }

    @Override
    protected void onWindowVisibilityChanged(int visibility) {
        super.onWindowVisibilityChanged(visibility);
        running = visibility == VISIBLE && isAttachedToWindow();
        handler.removeCallbacks(tick);
        if (running) handler.post(tick);
    }

    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        if (atlas == null || atlas.isRecycled()) return;
        int cellWidth = atlas.getWidth() / COLUMNS;
        int cellHeight = atlas.getHeight() / ROWS;
        int safeFrame = reduceMotion ? 0 : Math.min(frame, COLUMNS - 1);
        int left = safeFrame * cellWidth;
        int top = state.row * cellHeight;
        source.set(left, top, left + cellWidth, top + cellHeight);

        float scale = Math.min((float) getWidth() / cellWidth, (float) getHeight() / cellHeight);
        int drawWidth = Math.round(cellWidth * scale);
        int drawHeight = Math.round(cellHeight * scale);
        int x = (getWidth() - drawWidth) / 2;
        int y = getHeight() - drawHeight;
        destination.set(x, y, x + drawWidth, y + drawHeight);
        canvas.drawBitmap(atlas, source, destination, paint);
    }
}
