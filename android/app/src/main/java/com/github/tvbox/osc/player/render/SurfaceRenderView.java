package com.github.tvbox.osc.player.render;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.PixelFormat;
import android.util.AttributeSet;
import android.view.SurfaceHolder;
import android.view.SurfaceView;
import android.view.View;

import androidx.annotation.NonNull;

import com.github.tvbox.osc.util.LOG;

import xyz.doikki.videoplayer.player.AbstractPlayer;
import xyz.doikki.videoplayer.render.IRenderView;
import xyz.doikki.videoplayer.render.MeasureHelper;

public class SurfaceRenderView extends SurfaceView implements IRenderView, SurfaceHolder.Callback {
    private MeasureHelper mMeasureHelper;

    private AbstractPlayer mMediaPlayer;

    public SurfaceRenderView(Context context) {
        super(context);
    }

    public SurfaceRenderView(Context context, AttributeSet attrs) {
        super(context, attrs);
    }

    public SurfaceRenderView(Context context, AttributeSet attrs, int defStyleAttr) {
        super(context, attrs, defStyleAttr);
    }

    {
        mMeasureHelper = new MeasureHelper();
        SurfaceHolder surfaceHolder = getHolder();
        // 只在构造时注册一次，避免 resume/rebind 再叠一层 callback。
        surfaceHolder.addCallback(this);
        surfaceHolder.setFormat(PixelFormat.RGBA_8888);
    }

    @Override
    public void attachToPlayer(@NonNull AbstractPlayer player) {
        this.mMediaPlayer = player;
        // 新 View 有时会先出 Surface 再 attach，这里补一次绑定，避免空窗期。
        bindHolder(getHolder());
    }

    @Override
    public void setVideoSize(int videoWidth, int videoHeight) {
        if (videoWidth > 0 && videoHeight > 0) {
            mMeasureHelper.setVideoSize(videoWidth, videoHeight);
            requestLayout();
        }
    }

    @Override
    public void setVideoRotation(int degree) {
        mMeasureHelper.setVideoRotation(degree);
        setRotation(degree);
    }

    @Override
    public void setScaleType(int scaleType) {
        mMeasureHelper.setScreenScale(scaleType);
        requestLayout();
    }

    @Override
    public View getView() {
        return this;
    }

    @Override
    public Bitmap doScreenShot() {
        return null;
    }

    @Override
    public void release() {
        // 重绑时旧 View 被拆掉不得 setDisplay(null)，否则会清掉新 Surface。
        // 先丢掉播放器引用，surfaceDestroyed 就不会误解绑。
        mMediaPlayer = null;
        try {
            getHolder().removeCallback(this);
        } catch (Throwable ignored) {
        }
    }

    @Override
    protected void onMeasure(int widthMeasureSpec, int heightMeasureSpec) {
        int[] measuredSize = mMeasureHelper.doMeasure(widthMeasureSpec, heightMeasureSpec);
        setMeasuredDimension(measuredSize[0], measuredSize[1]);
    }

    @Override
    public void surfaceCreated(SurfaceHolder holder) {
        // 小窗↔全屏会销毁旧 Surface 并立刻创建新 Surface。
        // 必须在 created 时绑定，不能只等 surfaceChanged（同尺寸时可能不回调）。
        LOG.i("echo-surface-created valid=" + (holder != null && holder.getSurface() != null && holder.getSurface().isValid()));
        bindHolder(holder);
    }

    @Override
    public void surfaceChanged(SurfaceHolder holder, int format, int width, int height) {
        if (width <= 0 || height <= 0) {
            return;
        }
        LOG.i("echo-surface-changed w=" + width + " h=" + height);
        bindHolder(holder);
    }

    @Override
    public void surfaceDestroyed(SurfaceHolder holder) {
        LOG.i("echo-surface-destroyed");
        // 小窗↔全屏只改容器尺寸时，旧 Surface 销毁后马上会 surfaceCreated。
        // 这里 setDisplay(null) 会让 IJK 硬解丢掉输出，MuMu/部分真机上就是绿屏。
        // 真正释放走 release()，那时 mMediaPlayer 已经被置空。
    }

    private void bindHolder(SurfaceHolder holder) {
        if (mMediaPlayer == null || holder == null) {
            return;
        }
        if (holder.getSurface() == null || !holder.getSurface().isValid()) {
            return;
        }
        try {
            mMediaPlayer.setDisplay(holder);
        } catch (Throwable t) {
            LOG.i("echo-surface-bind-fail " + t);
        }
    }

    private void unbindPlayer() {
        if (mMediaPlayer == null) {
            return;
        }
        try {
            mMediaPlayer.setDisplay(null);
        } catch (Throwable ignored) {
        }
    }
}
