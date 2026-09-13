package kr.voicezerotrust.pilot;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.text.InputType;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

public class MainActivity extends Activity {
    private EditText server, token, room;
    private TextView status, report;
    private Button connect, analyze;
    private final Handler handler = new Handler();
    private final Runnable refresh = new Runnable() {
        @Override public void run() {
            status.setText(CallService.status);
            report.setText(CallService.report);
            connect.setEnabled(!CallService.active);
            analyze.setEnabled(CallService.connected && !CallService.analyzing);
            handler.postDelayed(this, 300);
        }
    };

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        ScrollView scroll = new ScrollView(this);
        LinearLayout body = new LinearLayout(this);
        body.setOrientation(LinearLayout.VERTICAL);
        int pad = (int) (20 * getResources().getDisplayMetrics().density);
        body.setPadding(pad, pad * 2, pad, pad);
        body.setBackgroundColor(Color.rgb(244, 247, 251));
        scroll.addView(body);
        setContentView(scroll);
        TextView title = text(body, "VoiceZeroTrust", 28);
        title.setTextColor(Color.rgb(22, 52, 78));
        text(body, "실제 기기 통화 실험 · Android", 17);
        text(body, "두 기기 또는 휴대폰–PC를 같은 방에 연결하세요. 앱 내 음성 통화이며 기존 전화번호 수신은 지원하지 않습니다.", 15);
        server = field(body, "서버 주소", "http://192.168.1.10:8765", false);
        room = field(body, "방 이름", "phone-test", false);
        token = field(body, "서버 연결 키 (PC 실행 화면)", "", true);
        server.setText(getPreferences(MODE_PRIVATE).getString("server", ""));
        room.setText(getPreferences(MODE_PRIVATE).getString("room", "phone-test"));
        text(body, "첫 10초 자동 분석 / 버튼을 누른 뒤 10초 재분석. 분석 구간 외 음성은 탐지용으로 보관하지 않습니다. 통화를 위해 음성은 PC 서버를 경유합니다. HTTP 연결은 신뢰하는 테스트 네트워크에서만 사용하세요.", 14);
        connect = button(body, "실험 통화 연결", () -> {
            if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, 1);
                return;
            }
            startCall();
        });
        analyze = button(body, "지금부터 10초 판별", () -> {
            Intent intent = new Intent(this, CallService.class).setAction("ANALYZE");
            startService(intent);
        });
        button(body, "통화 종료 · 수집 중단", () -> stopService(new Intent(this, CallService.class)));
        button(body, "일반 전화 접근 가능 여부", this::cellularCheck);
        status = text(body, "연결 대기", 19);
        report = text(body, "분석 결과가 여기에 표시됩니다.", 15);
        report.setTextIsSelectable(true);
        button(body, "테스트 결과 공유", () -> {
            Intent send = new Intent(Intent.ACTION_SEND).setType("text/plain");
            send.putExtra(Intent.EXTRA_TEXT, "VoiceZeroTrust pilot\n" + Build.MANUFACTURER + " " + Build.MODEL
                + " / Android " + Build.VERSION.RELEASE + "\n" + CallService.status + "\n" + CallService.report);
            startActivity(Intent.createChooser(send, "음성 없이 결과 텍스트 공유"));
        });
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 2);
        }
    }

    private void startCall() {
        try {
            String endpoint = Endpoint.websocket(server.getText().toString(), room.getText().toString());
            if (token.getText().length() < 16) throw new IllegalArgumentException("PC에 표시된 16자 이상의 연결 키를 입력하세요.");
            getPreferences(MODE_PRIVATE).edit().putString("server", server.getText().toString())
                .putString("room", room.getText().toString()).apply();
            Intent intent = new Intent(this, CallService.class).setAction("CONNECT")
                .putExtra("endpoint", endpoint).putExtra("token", token.getText().toString());
            startForegroundService(intent);
        } catch (IllegalArgumentException e) {
            new AlertDialog.Builder(this).setMessage(e.getMessage()).setPositiveButton("확인", null).show();
        }
    }

    private void cellularCheck() {
        boolean granted = checkSelfPermission("android.permission.CAPTURE_AUDIO_OUTPUT") == PackageManager.PERMISSION_GRANTED;
        String message = granted
            ? "시스템 통화 권한이 감지됐습니다. 이 실험 앱에는 셀룰러 캡처 구현이 없으므로 별도 기기 검증이 필요합니다."
            : "통화 음성 권한 없음: 이 일반 설치 앱은 기존 전화의 상대방 음성을 직접 가져올 수 없습니다. 첫 10초·수동 10초 모두 동일합니다. 이 검사는 권한 확인이며 실제 셀룰러 음성을 수집하지 않습니다.";
        new AlertDialog.Builder(this).setTitle("일반 전화 연동 진단").setMessage(message).setPositiveButton("확인", null).show();
    }

    @Override public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(requestCode, permissions, results);
        if (requestCode == 1 && results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) startCall();
    }
    @Override public void onResume() { super.onResume(); handler.post(refresh); }
    @Override public void onPause() { handler.removeCallbacks(refresh); super.onPause(); }

    private TextView text(LinearLayout body, String label, int size) {
        TextView view = new TextView(this);
        view.setText(label); view.setTextSize(size); view.setPadding(0, 12, 0, 12);
        body.addView(view); return view;
    }
    private EditText field(LinearLayout body, String label, String hint, boolean secret) {
        text(body, label, 14);
        EditText view = new EditText(this);
        view.setSingleLine(true); view.setHint(hint);
        view.setInputType(secret ? InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD
            : InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        body.addView(view); return view;
    }
    private Button button(LinearLayout body, String label, Runnable action) {
        Button view = new Button(this); view.setText(label);
        view.setOnClickListener(v -> action.run()); body.addView(view); return view;
    }
}
