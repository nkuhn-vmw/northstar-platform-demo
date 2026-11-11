// Hub's on-platform transport. The bound MCP Gateway owns OAuth and credentials.
package main

import (
	"errors"
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"strings"
	"time"
)

func handler(target *url.URL, transport http.RoundTripper) http.Handler {
	proxy := &httputil.ReverseProxy{
		Transport:     transport,
		FlushInterval: -1,
		Rewrite: func(r *httputil.ProxyRequest) {
			r.SetURL(target)
			r.Out.URL.Path = target.Path
			r.Out.URL.RawPath = target.RawPath
			r.Out.URL.RawQuery = ""
			r.Out.Host = target.Host
			allowed := http.Header{}
			for _, key := range []string{"Authorization", "Accept", "Content-Type", "Mcp-Session-Id", "Mcp-Protocol-Version", "Last-Event-ID"} {
				if values := r.Out.Header.Values(key); len(values) > 0 {
					allowed[http.CanonicalHeaderKey(key)] = values
				}
			}
			r.Out.Header = allowed
		},
		ModifyResponse: func(r *http.Response) error {
			if r.StatusCode >= 300 && r.StatusCode < 400 {
				return errors.New("unexpected upstream redirect")
			}
			r.Header.Del("Set-Cookie")
			return nil
		},
		ErrorHandler: func(w http.ResponseWriter, _ *http.Request, _ error) {
			// Errors can contain URLs and credentials. Return a fixed diagnostic.
			http.Error(w, "Hub MCP unavailable", http.StatusBadGateway)
		},
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/health" {
			w.WriteHeader(http.StatusOK)
			return
		}
		if r.URL.Path != "/mcp" {
			http.NotFound(w, r)
			return
		}
		if r.Method != http.MethodGet && r.Method != http.MethodPost && r.Method != http.MethodDelete {
			w.WriteHeader(http.StatusMethodNotAllowed)
			return
		}
		if !strings.HasPrefix(strings.ToLower(r.Header.Get("Authorization")), "bearer ") || len(strings.TrimSpace(r.Header.Get("Authorization")[7:])) == 0 {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}
		proxy.ServeHTTP(w, r)
	})
}

func main() {
	target, err := url.Parse(os.Getenv("HUB_MCP_URL"))
	if err != nil || target.Scheme != "https" || target.Host == "" || target.User != nil || target.RawQuery != "" || target.Fragment != "" {
		log.Fatal("HUB_MCP_URL must be an HTTPS endpoint without credentials, query or fragment")
	}
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.ResponseHeaderTimeout = 30 * time.Second
	server := &http.Server{Addr: ":" + port, Handler: handler(target, transport), ReadHeaderTimeout: 10 * time.Second}
	log.Fatal(server.ListenAndServe())
}
