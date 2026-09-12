package com.github.tvbox.osc.player;

import android.content.Context;
import android.util.AttributeSet;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import master.flame.danmaku.controller.DrawHandler;
import master.flame.danmaku.danmaku.model.BaseDanmaku;
import master.flame.danmaku.danmaku.model.DanmakuTimer;
import master.flame.danmaku.ui.widget.DanmakuView;
import xyz.doikki.videoplayer.player.AbstractPlayer;
import xyz.doikki.videoplayer.player.VideoView;

public class MyVideoView extends VideoView implements DrawHandler.Callback {
    private DanmakuView danmuView;

    public MyVideoView(@NonNull Context context) {
        super(context, null);
    }

    public MyVideoView(@NonNull Context context, @Nullable AttributeSet attrs) {
        super(context, attrs, 0);
    }

    public MyVideoView(@NonNull Context context, @Nullable AttributeSet attrs, int defStyleAttr) {
        super(context, attrs, defStyleAttr);
    }

    public AbstractPlayer getMediaPlayer() {
        return mMediaPlayer;
    }

    /**
     * 详情预览小窗/全屏切换后重建 render view，并把当前播放器重新绑到新 Surface。
     * 不释放播放器，也不改播放/暂停状态；新 Surface 未创建前由 RenderView 自己等待绑定。
     */
    public void rebindDisplay() {
        if (mMediaPlayer == null) {
            return;
        }
        com.github.tvbox.osc.util.LOG.i("echo-rebind-display state=" + getCurrentPlayState()
                + " playing=" + isPlaying()
                + " size=" + mVideoSize[0] + "x" + mVideoSize[1]);
        addDisplay();
        if (mRenderView != null) {
            mRenderView.setScaleType(mCurrentScreenScaleType);
            if (mVideoSize[0] > 0 && mVideoSize[1] > 0) {
                mRenderView.setVideoSize(mVideoSize[0], mVideoSize[1]);
            }
        }
    }

    public int[] getVideoSize() {
        return mVideoSize;
    }

    @Override
    public void seekTo(long pos) {
        super.seekTo(pos);
        if (haveDanmu()) danmuView.seekTo(pos);
    }

    @Override
    public void resume() {
        super.resume();
        if (haveDanmu()) danmuView.resume();
    }

    @Override
    public void start() {
        super.start();
        if (haveDanmu()) danmuView.resume();
    }

    @Override
    public void pause() {
        super.pause();
        if (haveDanmu()) danmuView.pause();
    }

    @Override
    public void release() {
        super.release();
        if (haveDanmu()) danmuView.release();
    }

    private boolean haveDanmu() {
        return danmuView != null && danmuView.isPrepared();
    }

    public void setDanmuView(DanmakuView view) {
        danmuView = view;
        if (danmuView != null) danmuView.setCallback(this);
    }

    public DanmakuView getDanmuView() {
        return danmuView;
    }

    @Override
    public void prepared() {
        post(() -> {
            if (danmuView == null) return;
            if (isPlaying() && danmuView.isPrepared()) {
                danmuView.start(getCurrentPosition());
            }
        });
    }

    @Override
    public void updateTimer(DanmakuTimer timer) {
    }

    @Override
    public void danmakuShown(BaseDanmaku danmaku) {
    }

    @Override
    public void drawingFinished() {
    }
}
