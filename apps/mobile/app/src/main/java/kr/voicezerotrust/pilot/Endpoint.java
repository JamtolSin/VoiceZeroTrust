package kr.voicezerotrust.pilot;

import java.net.URI;

/** Lab cleartext is allowed only on explicit private IPv4 addresses. */
public final class Endpoint {
    private Endpoint() {}

    public static String websocket(String input, String room) {
        URI uri = URI.create(input.trim());
        String scheme = uri.getScheme();
        String host = uri.getHost();
        if (host == null || uri.getUserInfo() != null || uri.getQuery() != null
                || uri.getFragment() != null || !(uri.getPath().isEmpty() || uri.getPath().equals("/"))) {
            throw new IllegalArgumentException("서버 주소는 경로 없이 http://192.168.1.10:8765 형태로 입력하세요.");
        }
        if (!"https".equals(scheme) && !("http".equals(scheme) && privateAddress(host))) {
            throw new IllegalArgumentException("HTTP는 사설 IPv4·Tailscale 주소만 허용합니다. 외부 서버는 HTTPS가 필요합니다.");
        }
        if (!room.matches("[A-Za-z0-9-]{4,40}")) {
            throw new IllegalArgumentException("방 이름은 영문·숫자·하이픈 4~40자입니다.");
        }
        return ("https".equals(scheme) ? "wss" : "ws") + "://" + uri.getRawAuthority() + "/call/" + room;
    }

    static boolean privateAddress(String host) {
        String[] parts = host.split("\\.");
        if (parts.length != 4) return false;
        int[] bytes = new int[4];
        try {
            for (int i = 0; i < 4; i++) {
                if (!parts[i].matches("[0-9]{1,3}")) return false;
                bytes[i] = Integer.parseInt(parts[i]);
                if (bytes[i] > 255) return false;
            }
        } catch (NumberFormatException e) { return false; }
        return bytes[0] == 10 || bytes[0] == 127
            || (bytes[0] == 192 && bytes[1] == 168)
            || (bytes[0] == 172 && bytes[1] >= 16 && bytes[1] <= 31)
            || (bytes[0] == 100 && bytes[1] >= 64 && bytes[1] <= 127);
    }
}
