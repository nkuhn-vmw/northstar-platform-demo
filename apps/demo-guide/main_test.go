package main

import (
	"encoding/base64"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestSSORequiresValidSingleBinding(t *testing.T) {
	for _, raw := range []string{"", `{}`, `{"p-identity":[]}`, `{"p-identity":[{"credentials":{"auth_domain":"http://bad","client_id":"id","client_secret":"secret"}}]}`} {
		if _, err := sso(raw); err == nil {
			t.Fatal("accepted invalid binding")
		}
	}
	c, err := sso(`{"p-identity":[{"credentials":{"auth_domain":"https://sso.test","client_id":"id","client_secret":"secret"}}]}`)
	if err != nil || c.ID != "id" {
		t.Fatal("valid binding rejected")
	}
}
func TestEmailPolicyIsExplicit(t *testing.T) {
	for _, v := range []string{"", "*@test.com", "good@test.com,*", "good@test.com\nother@test.com"} {
		if _, done, err := emailArgs(v); err == nil {
			done()
			t.Fatal("accepted", v)
		}
	}
	for _, v := range []string{"*", "colleague@test.com"} {
		args, done, err := emailArgs(v)
		if err != nil || len(args) != 1 {
			t.Fatal("rejected valid policy")
		}
		done()
	}
}
func TestGuideEscapesConfigAndHasNoCredentialSurface(t *testing.T) {
	h := handler(Page{Org: "<script>oops</script>", Agent: "javascript:alert(1)", HubEnabled: true, CredentialStore: true})
	w := httptest.NewRecorder()
	h.ServeHTTP(w, httptest.NewRequest("GET", "/", nil))
	b := w.Body.String()
	if strings.Contains(b, "<script>oops") || strings.Contains(b, `href="javascript:`) {
		t.Fatal("configuration injection")
	}
	if !strings.Contains(b, "Never paste a token into chat") || !strings.Contains(b, "Scope credential to current user") {
		t.Fatal("missing token instructions")
	}
	if !strings.Contains(w.Header().Get("Content-Security-Policy"), "form-action 'none'") {
		t.Fatal("missing CSP")
	}
	w = httptest.NewRecorder()
	h.ServeHTTP(w, httptest.NewRequest("GET", "/missing", nil))
	if w.Code != 404 {
		t.Fatal("missing path not rejected")
	}
}

func TestProxyEnvironmentRejectsInheritedOverrides(t *testing.T) {
	t.Setenv("VCAP_SERVICES", "secret-bindings")
	t.Setenv("OAUTH2_PROXY_EMAIL_DOMAINS", "*")
	t.Setenv("OAUTH2_PROXY_SKIP_AUTH_ROUTES", ".*")
	env := proxyEnv(credential{ID: "id", Secret: "synthetic-secret"})
	for _, v := range env {
		if strings.HasPrefix(v, "VCAP_") || strings.HasPrefix(v, "OAUTH2_PROXY_EMAIL_DOMAINS=") || strings.HasPrefix(v, "OAUTH2_PROXY_SKIP_AUTH_ROUTES=") {
			t.Fatal("inherited unsafe environment")
		}
		if strings.HasPrefix(v, "OAUTH2_PROXY_COOKIE_SECRET=") {
			b, err := base64.RawURLEncoding.DecodeString(strings.TrimPrefix(v, "OAUTH2_PROXY_COOKIE_SECRET="))
			if err != nil || len(b) != 32 {
				t.Fatal("invalid cookie key")
			}
		}
	}
}
func TestAssetsAndDisabledConnections(t *testing.T) {
	h := handler(Page{})
	for _, path := range []string{"/style.css", "/guide.js", "/architecture.svg"} {
		w := httptest.NewRecorder()
		h.ServeHTTP(w, httptest.NewRequest("GET", path, nil))
		if w.Code != 200 || w.Body.Len() == 0 || w.Header().Get("X-Content-Type-Options") != "nosniff" {
			t.Fatal("invalid asset", path)
		}
	}
	w := httptest.NewRecorder()
	h.ServeHTTP(w, httptest.NewRequest("GET", "/index.html", nil))
	if w.Code != 404 {
		t.Fatal("raw template exposed")
	}
	w = httptest.NewRecorder()
	h.ServeHTTP(w, httptest.NewRequest("GET", "/", nil))
	b := w.Body.String()
	if strings.Contains(b, "GitHub cannot read a repository") || strings.Contains(b, "Hub returns no inventory") || strings.Contains(b, "Deployment checks passed") {
		t.Fatal("incorrect disabled/state content")
	}
}
