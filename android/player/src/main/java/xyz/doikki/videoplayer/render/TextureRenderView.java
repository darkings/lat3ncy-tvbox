package xyz.doikki.videoplayer.render;

import android.annotation.SuppressLint;
import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.SurfaceTexture;
import android.view.Surface;
import android.view.TextureView;
import android.view.View;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import xyz.doikki.videoplayer.player.AbstractPlayer;

@SuppressLint("ViewConstructor")
public class TextureRenderView extends TextureView implements IRenderView, TextureView.SurfaceTextureListener {
    private MeasureHelper mMeasureHelper;
    private SurfaceTexture mSurfaceTexture;

    @Nullable
    private AbstractPlayer mMediaPlayer;
    private Surface mSurface;

    public TextureRenderView(Context context) {
        super(context);
    }

    {
        mMeasureHelper = new MeasureHelper();
        setSurfaceTextureListener(this);
    }

    @Override
    public void attachToPlayer(@NonNull AbstractPlayer player) {
        this.mMediaPlayer = player;
        // SurfaceTexture 若已就绪，立刻绑到新播放器，避免 rebind 空窗。
        if (mSurface != null && mSurface.isValid()) {
            bindSurface();
        }
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
        return getBitmap();
    }

    @Override
    public void release() {
        // 重绑时旧 View 被拆掉不得 setSurface(null)，否则会清掉新 Surface。
        mMediaPlayer = null;
        releaseSurface();
    }

    @Override
    protected void onMeasure(int widthMeasureSpec, int heightMeasureSpec) {
        int[] measuredSize = mMeasureHelper.doMeasure(widthMeasureSpec, heightMeasureSpec);
        setMeasuredDimension(measuredSize[0], measuredSize[1]);
    }

    @Override
    public void onSurfaceTextureAvailable(SurfaceTexture surfaceTexture, int width, int height) {
        // 小窗↔全屏会换新 TextureView。旧 SurfaceTexture 尺寸/缓冲已失效，
        // 不能再 setSurfaceTexture 复用，否则画面会一直黑。
        releaseSurface();
        mSurfaceTexture = surfaceTexture;
        mSurface = new Surface(surfaceTexture);
        bindSurface();
    }

    @Override
    public void onSurfaceTextureSizeChanged(SurfaceTexture surface, int width, int height) {
        bindSurface();
    }

    @Override
    public boolean onSurfaceTextureDestroyed(SurfaceTexture surface) {
        unbindPlayer();
        releaseSurface();
        // 返回 true：交给系统释放，避免旧缓冲在下一次 available 时被复用。
        return true;
    }

    @Override
    public void onSurfaceTextureUpdated(SurfaceTexture surface) {

    }

    private void bindSurface() {
        if (mMediaPlayer == null || mSurface == null || !mSurface.isValid()) {
            return;
        }
        try {
            mMediaPlayer.setSurface(mSurface);
        } catch (Throwable ignored) {
        }
    }

    private void unbindPlayer() {
        if (mMediaPlayer == null) {
            return;
        }
        try {
            mMediaPlayer.setSurface(null);
        } catch (Throwable ignored) {
        }
    }

    private void releaseSurface() {
        if (mSurface != null) {
            try {
                mSurface.release();
            } catch (Throwable ignored) {
            }
            mSurface = null;
        }
        mSurfaceTexture = null;
    }
}
