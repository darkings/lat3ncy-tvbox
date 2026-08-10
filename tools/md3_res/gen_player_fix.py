# -*- coding: utf-8 -*-
"""VodController：隐藏播放器无效技术值（0bps / 0x0）。"""

from pathlib import Path

path = Path(
    "android/app/src/main/java/com/github/tvbox/osc/player/controller/VodController.java"
)
data = path.read_text(encoding="utf-8")

old = """            long mSpeed = mControlWrapper.getTcpSpeed();
            String speed = PlayerHelper.getDisplaySpeed(mSpeed,false);
            String speedBps = PlayerHelper.getDisplaySpeedBps(mSpeed,true);
            mPlayLoadNetSpeedRightTop.setText(speedBps);
            mPlayLoadNetSpeed.setText(speed);
            net_play_speed.setText(speedBps);
            int[] mVideoSizes = mControlWrapper.getVideoSize();
            String width = Integer.toString(mVideoSizes[0]);
            String height = Integer.toString(mVideoSizes[1]);
            mVideoSize.setText("[ " + width + " X " + height +" ]");"""

new = """            long mSpeed = mControlWrapper.getTcpSpeed();
            String speed = PlayerHelper.getDisplaySpeed(mSpeed,false);
            // show=false：速度为 0 时返回空串，不显示 0bps 无效值（审计 QA-10）
            String speedBps = PlayerHelper.getDisplaySpeedBps(mSpeed,false);
            mPlayLoadNetSpeedRightTop.setText(speedBps);
            mPlayLoadNetSpeed.setText(speed);
            net_play_speed.setText(speedBps);
            int[] mVideoSizes = mControlWrapper.getVideoSize();
            if (mVideoSizes[0] > 0 && mVideoSizes[1] > 0) {
                mVideoSize.setText("[ " + mVideoSizes[0] + " X " + mVideoSizes[1] + " ]");
                mVideoSize.setVisibility(View.VISIBLE);
            } else {
                // 未知分辨率不显示 [ 0 X 0 ]
                mVideoSize.setVisibility(View.GONE);
            }"""

assert old in data, "未找到目标代码段"
data = data.replace(old, new)
path.write_text(data, encoding="utf-8")
print("VodController 修改完成")
