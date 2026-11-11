package main

import (
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
)

func TestRelayForwardsMCPAndIsolatesCredentials(t *testing.T) {
	calls := 0
	upstream := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		if r.URL.Path != "/hub/mcp" || r.URL.RawQuery != "" || r.Header.Get("Authorization") != "Bearer test-user" {
			t.Errorf("incorrect MCP target or authorization")
		}
		if r.Header.Get("Cookie") != "" || r.Header.Get("X-Forwarded-User-Token") != "" || r.Header.Get("X-Identity-Token") != "" {
			t.Error("browser or platform credentials leaked")
		}
		body, _ := io.ReadAll(r.Body)
		if string(body) != `{"jsonrpc":"2.0","id":1,"method":"tools/list"}` {
			t.Error("MCP body changed")
		}
		w.Header().Set("Content-Type", "text/event-stream")
		w.Header().Set("Mcp-Session-Id", "test-session")
		w.Header().Set("Set-Cookie", "upstream-cookie")
		io.WriteString(w, "event: message\ndata: {\"result\":{\"tools\":[]}}\n\n")
	}))
	defer upstream.Close()
	target, _ := url.Parse(upstream.URL + "/hub/mcp")
	h := handler(target, upstream.Client().Transport)
	for path, status := range map[string]int{"/mcp": http.StatusUnauthorized, "/other": http.StatusNotFound} {
		w := httptest.NewRecorder()
		h.ServeHTTP(w, httptest.NewRequest("POST", path, nil))
		if w.Code != status {
			t.Fatalf("unexpected rejection %d", w.Code)
		}
	}
	if calls != 0 {
		t.Fatal("denied requests reached Hub")
	}
	r := httptest.NewRequest("POST", "/mcp?destination=elsewhere", strings.NewReader(`{"jsonrpc":"2.0","id":1,"method":"tools/list"}`))
	r.Header.Set("Authorization", "Bearer test-user")
	r.Header.Set("Cookie", "presenter-cookie")
	r.Header.Set("X-Identity-Token", "platform-token")
	r.Header.Set("X-Forwarded-User-Token", "platform-token")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != 200 || calls != 1 || w.Header().Get("Mcp-Session-Id") != "test-session" || w.Header().Get("Set-Cookie") != "" || !strings.Contains(w.Body.String(), "event: message") {
		t.Fatal("MCP response or header isolation failed")
	}
}

func TestRelayRejectsUpstreamRedirect(t *testing.T) {
	upstream := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, "https://unrelated.invalid/", http.StatusTemporaryRedirect)
	}))
	defer upstream.Close()
	target, _ := url.Parse(upstream.URL)
	r := httptest.NewRequest("GET", "/mcp", nil)
	r.Header.Set("Authorization", "Bearer test-user")
	w := httptest.NewRecorder()
	handler(target, upstream.Client().Transport).ServeHTTP(w, r)
	if w.Code != http.StatusBadGateway || w.Header().Get("Location") != "" {
		t.Fatal("upstream redirect exposed to caller")
	}
}

func TestRelayRejectsUntrustedTLS(t *testing.T) {
	upstream := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { t.Error("untrusted request reached Hub") }))
	defer upstream.Close()
	target, _ := url.Parse(upstream.URL)
	request := httptest.NewRequest("POST", "/mcp", nil)
	request.Header.Set("Authorization", "Bearer test-user")
	response := httptest.NewRecorder()
	handler(target, http.DefaultTransport).ServeHTTP(response, request)
	if response.Code != http.StatusBadGateway {
		t.Fatalf("untrusted TLS accepted: %d", response.Code)
	}
}
