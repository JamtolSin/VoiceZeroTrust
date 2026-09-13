package kr.voicezerotrust.pilot;

import org.junit.Test;
import static org.junit.Assert.*;

public class EndpointTest {
    @Test public void permitsPrivateLanAndTls() {
        assertEquals("ws://192.168.1.10:8765/call/test-room", Endpoint.websocket("http://192.168.1.10:8765", "test-room"));
        assertEquals("wss://example.com/call/test", Endpoint.websocket("https://example.com/", "test"));
        assertTrue(Endpoint.privateAddress("100.85.145.52"));
        assertFalse(Endpoint.privateAddress("100.128.0.1"));
        assertFalse(Endpoint.privateAddress("172.32.0.1"));
    }
    @Test public void rejectsUnsafeUrlsAndRooms() {
        for (String url : new String[]{"http://example.com", "http://8.8.8.8", "http://user:pass@192.168.1.2", "http://192.168.1.2/path", "https://example.com?token=secret", "file:///tmp", "http://10.999.1.1"}) {
            assertThrows(IllegalArgumentException.class, () -> Endpoint.websocket(url, "test"));
        }
        assertThrows(IllegalArgumentException.class, () -> Endpoint.websocket("https://example.com", "../room"));
    }
}
