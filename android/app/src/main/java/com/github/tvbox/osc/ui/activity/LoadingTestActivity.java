package com.github.tvbox.osc.ui.activity;

import android.os.Bundle;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import androidx.appcompat.app.AppCompatActivity;
import com.github.tvbox.osc.R;

public class LoadingTestActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(100, 100, 100, 100);
        
        // 4 个变体
        ProgressBar p1 = new ProgressBar(this);
        p1.setIndeterminateDrawable(getDrawable(R.drawable.ponyo_loading_play));
        layout.addView(p1);
        
        ProgressBar p2 = new ProgressBar(this);
        p2.setIndeterminateDrawable(getDrawable(R.drawable.ponyo_loading_channel));
        layout.addView(p2);
        
        ProgressBar p3 = new ProgressBar(this);
        p3.setIndeterminateDrawable(getDrawable(R.drawable.ponyo_loading_content));
        layout.addView(p3);
        
        ProgressBar p4 = new ProgressBar(this);
        p4.setIndeterminateDrawable(getDrawable(R.drawable.ponyo_loading_search));
        layout.addView(p4);
        
        setContentView(layout);
    }
}