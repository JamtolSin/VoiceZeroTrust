package kr.voicezerotrust.pilot;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.media.AudioAttributes;
import android.media.AudioFocusRequest;
import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioRecord;
import android.media.AudioTrack;
import android.media.MediaRecorder;
import android.media.audiofx.AcousticEchoCanceler;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;
import okio.ByteString;
import org.json.JSONObject;

public class CallService extends Service {
    public static volatile boolean active = false, connected = false, analyzing = false;
    public static volatile String status = "연결 대기", report = "아직 판별하지 않았습니다.";
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ArrayBlockingQueue<byte[]> playback = new ArrayBlockingQueue<>(15);
    private final OkHttpClient client = new OkHttpClient.Builder().pingInterval(15, TimeUnit.SECONDS).build();
    private volatile boolean stopped;
    private volatile WebSocket socket;
    private volatile AudioRecord recorder;
    private volatile AudioTrack track;
    private AcousticEchoCanceler echoCanceler;
    private AudioManager audio;
    private AudioFocusRequest focus;
    private int previousMode;
    private boolean previousSpeaker;
    private long captureDeadline;
    private final Runnable ticker = new Runnable() {
        private int ticks;
        @Override public void run() {
            if (stopped) return;
            if (captureDeadline > 0) {
                long remaining = Math.max(0, (captureDeadline - android.os.SystemClock.elapsedRealtime() + 999) / 1000);
                status = remaining > 0 ? "상대방 음성 수집 중 · " + remaining + "초 남음" : "수집 종료 · 분석 응답 대기";
            }
            if (++ticks % 15 == 0 && socket != null) socket.send("{\"type\":\"ping\"}");
            main.postDelayed(this, 1000);
        }
    };

    @Override public IBinder onBind(Intent intent) { return null; }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null) { stopSelf(); return START_NOT_STICKY; }
        if ("ANALYZE".equals(intent.getAction())) {
            if (connected && !analyzing && socket != null) socket.send("{\"type\":\"analyze\"}");
            else if (!active) stopSelf();
            return START_NOT_STICKY;
        }
        if ("STOP".equals(intent.getAction())) { stopSelf(); return START_NOT_STICKY; }
        if (active) return START_NOT_STICKY;
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            status = "마이크 권한이 필요합니다."; stopSelf(); return START_NOT_STICKY;
        }
        active = true; connected = false; analyzing = false; stopped = false;
        status = "서버 연결 중"; report = "실험 결과 대기 · 미검출은 안전 판정이 아닙니다.";
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel("call", "실험 통화", NotificationManager.IMPORTANCE_LOW));
        PendingIntent open = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class), PendingIntent.FLAG_IMMUTABLE);
        PendingIntent end = PendingIntent.getService(this, 1, new Intent(this, CallService.class).setAction("STOP"), PendingIntent.FLAG_IMMUTABLE);
        Notification notification = new Notification.Builder(this, "call")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now).setContentTitle("VoiceZeroTrust 실험 통화")
            .setContentText("통화용 마이크 사용 중 · 눌러서 10초 판별")
            .setContentIntent(open).setOngoing(true).addAction(android.R.drawable.ic_menu_close_clear_cancel, "종료", end).build();
        if (Build.VERSION.SDK_INT >= 29) startForeground(1, notification,
            ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE | ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK);
        else startForeground(1, notification);
        main.post(ticker);
        String endpoint = intent.getStringExtra("endpoint");
        String key = intent.getStringExtra("token");
        if (endpoint == null || key == null) { fail("연결 설정이 없습니다."); return START_NOT_STICKY; }
        socket = client.newWebSocket(new Request.Builder().url(endpoint).build(), new WebSocketListener() {
            @Override public void onOpen(WebSocket webSocket, Response response) {
                if (stopped) { webSocket.cancel(); return; }
                try { webSocket.send(new JSONObject().put("token", key).toString()); }
                catch (Exception e) { fail("인증 요청 실패"); }
            }
            @Override public void onMessage(WebSocket webSocket, String text) {
                if (stopped) return;
                try {
                    JSONObject message = new JSONObject(text);
                    switch (message.optString("type")) {
                        case "waiting":
                            status = "상대방 대기 · PC 또는 두 번째 휴대폰을 연결하세요.";
                            new Thread(() -> prepareAudio(webSocket), "vzt-prepare").start();
                            break;
                        case "connected":
                            connected = true;
                            status = "실험 통화 연결됨 · 이어폰 사용 권장";
                            break;
                        case "capturing":
                            analyzing = true;
                            captureDeadline = android.os.SystemClock.elapsedRealtime() + message.optInt("seconds", 10) * 1000L;
                            status = "상대방 음성 10초 수집 시작";
                            break;
                        case "analyzing":
                            captureDeadline = 0;
                            status = "수집 종료 · 모델 분석 중 (첫 실행은 다운로드로 지연될 수 있음)";
                            break;
                        case "result":
                            captureDeadline = 0; analyzing = false;
                            status = "분석 응답 수신 · 통화는 계속됩니다.";
                            report = renderReport(message);
                            break;
                        case "error": status = message.optString("message"); break;
                        case "ended": fail(message.optString("message", "통화 종료")); break;
                        default: break;
                    }
                } catch (Exception e) { fail("서버 응답을 읽지 못했습니다."); }
            }
            @Override public void onMessage(WebSocket webSocket, ByteString bytes) {
                if (stopped) return;
                if (bytes.size() > 6400 || bytes.size() % 2 != 0) { fail("잘못된 음성 프레임"); return; }
                if (!playback.offer(bytes.toByteArray())) {
                    playback.poll(); playback.offer(bytes.toByteArray());
                }
            }
            @Override public void onClosing(WebSocket webSocket, int code, String reason) {
                webSocket.close(code, reason);
                fail("통화 종료: " + reason);
            }
            @Override public void onFailure(WebSocket webSocket, Throwable t, Response response) {
                fail("연결 실패: PC 서버 실행, 동일 Wi-Fi, 연결 키, 방화벽을 확인하세요.");
            }
        });
        return START_NOT_STICKY;
    }

    @SuppressLint("MissingPermission") // Permission checked before foreground service and again below.
    private void prepareAudio(WebSocket webSocket) {
        try {
            synchronized (this) {
                if (stopped) return;
                if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                    fail("마이크 권한이 취소됐습니다."); return;
                }
                audio = getSystemService(AudioManager.class);
                previousMode = audio.getMode(); previousSpeaker = audio.isSpeakerphoneOn();
                AudioAttributes attributes = new AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build();
                focus = new AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT)
                    .setAudioAttributes(attributes).setOnAudioFocusChangeListener(change -> {
                        if (change == AudioManager.AUDIOFOCUS_LOSS || change == AudioManager.AUDIOFOCUS_LOSS_TRANSIENT)
                            fail("다른 전화 또는 앱이 오디오를 사용하여 실험 통화를 종료했습니다.");
                    }, main).build();
                if (audio.requestAudioFocus(focus) != AudioManager.AUDIOFOCUS_REQUEST_GRANTED) {
                    fail("오디오 사용 권한을 얻지 못했습니다. 기존 전화를 종료하고 재시도하세요."); return;
                }
                audio.setMode(AudioManager.MODE_IN_COMMUNICATION);
                audio.setSpeakerphoneOn(true);
                int minRecord = AudioRecord.getMinBufferSize(16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT);
                recorder = new AudioRecord(MediaRecorder.AudioSource.VOICE_COMMUNICATION, 16000,
                    AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, Math.max(minRecord, 6400));
                if (recorder.getState() != AudioRecord.STATE_INITIALIZED) throw new IllegalStateException("microphone");
                if (AcousticEchoCanceler.isAvailable()) {
                    echoCanceler = AcousticEchoCanceler.create(recorder.getAudioSessionId());
                    if (echoCanceler != null) echoCanceler.setEnabled(true);
                }
                int minPlay = AudioTrack.getMinBufferSize(16000, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT);
                track = new AudioTrack.Builder().setAudioAttributes(attributes)
                    .setAudioFormat(new AudioFormat.Builder().setSampleRate(16000).setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT).build())
                    .setBufferSizeInBytes(Math.max(minPlay, 6400)).setTransferMode(AudioTrack.MODE_STREAM).build();
                if (track.getState() != AudioTrack.STATE_INITIALIZED) throw new IllegalStateException("speaker");
                track.play();
            }
            webSocket.send("{\"type\":\"ready\"}");
            new Thread(this::playAudio, "vzt-playback").start();
            while (!stopped && !connected) Thread.sleep(25);
            AudioRecord input = recorder;
            if (stopped || input == null) return;
            input.startRecording();
            if (input.getRecordingState() != AudioRecord.RECORDSTATE_RECORDING) throw new IllegalStateException("recording");
            byte[] frame = new byte[640];
            while (!stopped) {
                int read = input.read(frame, 0, frame.length);
                if (read <= 0) { if (!stopped) fail("마이크 입력 실패"); break; }
                if (webSocket.queueSize() > 32000 || !webSocket.send(ByteString.of(frame, 0, read))) {
                    fail("네트워크 지연으로 통화를 종료했습니다. 재연결하세요."); break;
                }
            }
        } catch (Exception e) { if (!stopped) fail("기기 오디오 초기화 또는 입력 실패. 마이크 권한과 다른 통화를 확인하세요."); }
    }

    private void playAudio() {
        try {
            while (!stopped) {
                byte[] frame = playback.poll(1, TimeUnit.SECONDS);
                AudioTrack output = track;
                if (frame != null && output != null) {
                    int offset = 0;
                    while (offset < frame.length && !stopped) {
                        int written = output.write(frame, offset, frame.length - offset);
                        if (written <= 0) throw new IllegalStateException("playback");
                        offset += written;
                    }
                }
            }
        } catch (Exception e) { if (!stopped) fail("상대방 음성 재생 실패"); }
    }

    private String renderReport(JSONObject event) throws Exception {
        JSONObject result = event.getJSONObject("report");
        JSONObject acoustic = result.optJSONObject("acoustic");
        JSONObject content = result.optJSONObject("content");
        JSONObject transcription = result.optJSONObject("transcription");
        StringBuilder text = new StringBuilder();
        text.append("분석 구간: ").append(event.optString("reason")).append(" / 수신 ")
            .append(String.format(java.util.Locale.KOREA, "%.2f초", event.optDouble("duration_seconds"))).append("\n\n");
        if (acoustic != null) {
            text.append("음향: ").append(acoustic.optString("status")).append(" · ").append(acoustic.optString("decision")).append("\n");
            if (!acoustic.isNull("fake_score")) text.append("합성 클래스 점수: ").append(acoustic.opt("fake_score")).append(" (사기 확률 아님)\n");
            text.append(acoustic.optString("message")).append("\n\n");
        }
        if (content != null) text.append("대화: ").append(content.optString("level", content.optString("status"))).append("\n");
        if (transcription != null) text.append("전사: ").append(transcription.optString("status")).append("\n").append(transcription.optString("text")).append("\n\n");
        text.append(result.optString("recommendation")).append("\n\n분석 ID: ").append(event.optString("id"));
        return text.toString();
    }

    private void fail(String message) {
        main.post(() -> { if (!stopped) { status = message; stopSelf(); } });
    }

    @Override public synchronized void onDestroy() {
        stopped = true; active = false; connected = false; analyzing = false;
        captureDeadline = 0; main.removeCallbacks(ticker);
        if (socket != null) { socket.cancel(); socket = null; }
        if (recorder != null) {
            try { recorder.stop(); } catch (IllegalStateException ignored) { }
            recorder.release(); recorder = null;
        }
        if (echoCanceler != null) { echoCanceler.release(); echoCanceler = null; }
        if (track != null) {
            try { track.stop(); } catch (IllegalStateException ignored) { }
            track.release(); track = null;
        }
        playback.clear();
        if (audio != null) {
            audio.setSpeakerphoneOn(previousSpeaker); audio.setMode(previousMode);
            if (focus != null) audio.abandonAudioFocusRequest(focus);
        }
        client.dispatcher().executorService().shutdown();
        client.connectionPool().evictAll();
        if (!status.contains("실패") && !status.contains("종료") && !status.contains("권한")) status = "통화 종료 · 분석용 수집 중단";
        stopForeground(STOP_FOREGROUND_REMOVE);
        super.onDestroy();
    }
}
