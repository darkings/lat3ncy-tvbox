package com.github.tvbox.osc.ui.activity;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.view.animation.DecelerateInterpolator;

import com.github.tvbox.osc.R;
import com.github.tvbox.osc.util.HawkConfig;
import com.orhanobut.hawk.Hawk;

public class SplashActivity extends Activity {
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable openHome = () -> {
        Intent intent = new Intent(SplashActivity.this, HomeActivity.class);
        intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        if (getIntent() != null && getIntent().getExtras() != null) {
            intent.putExtras(getIntent().getExtras());
        }
        startActivity(intent);
        if (!Hawk.get(HawkConfig.REDUCE_MOTION, false)) {
            overridePendingTransition(android.R.anim.fade_in, android.R.anim.fade_out);
        } else {
            overridePendingTransition(0, 0);
        }
        finish();
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                        | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY);
        setContentView(R.layout.activity_splash);
        boolean reduceMotion = Hawk.get(HawkConfig.REDUCE_MOTION, false);
        View scene = findViewById(R.id.splash_scene);
        View atmosphere = findViewById(R.id.splash_atmosphere);
        View hero = findViewById(R.id.splash_hero);
        View copy = findViewById(R.id.splash_copy);
        View title = findViewById(R.id.splash_title);
        View accent = findViewById(R.id.splash_accent);
        View tagline = findViewById(R.id.splash_tagline);
        if (reduceMotion) {
            scene.setAlpha(1f);
            atmosphere.setAlpha(1f);
            hero.setAlpha(1f);
            copy.setAlpha(1f);
            handler.post(openHome);
            return;
        }

        float density = getResources().getDisplayMetrics().density;
        DecelerateInterpolator ease = new DecelerateInterpolator(1.8f);
        scene.animate()
                .alpha(1f)
                .setDuration(260)
                .setInterpolator(ease)
                .start();
        atmosphere.animate()
                .alpha(1f)
                .setStartDelay(60)
                .setDuration(360)
                .setInterpolator(ease)
                .start();

        hero.setTranslationX(18f * density);
        hero.setScaleX(0.96f);
        hero.setScaleY(0.96f);
        hero.animate()
                .alpha(1f)
                .translationX(0f)
                .scaleX(1f)
                .scaleY(1f)
                .setStartDelay(80)
                .setDuration(320)
                .setInterpolator(ease)
                .withLayer()
                .start();

        copy.setAlpha(1f);
        copy.setTranslationY(8f * density);
        title.setAlpha(0f);
        accent.setAlpha(0f);
        tagline.setAlpha(0f);
        copy.animate()
                .translationY(0f)
                .setStartDelay(180)
                .setDuration(360)
                .setInterpolator(ease)
                .start();
        title.animate().alpha(1f).setStartDelay(180).setDuration(280).start();
        accent.animate().alpha(1f).setStartDelay(220).setDuration(300).start();
        tagline.animate().alpha(1f).setStartDelay(280).setDuration(320).start();

        handler.postDelayed(openHome, 1000);
    }

    @Override
    protected void onDestroy() {
        handler.removeCallbacks(openHome);
        super.onDestroy();
    }
}
