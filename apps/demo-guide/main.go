package main

import (
	"context"
	"crypto/sha256"
	"embed"
	"encoding/base64"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"html/template"
	"log"
	"net"
	"net/http"
	"net/mail"
	"net/url"
	"os"
	"os/exec"
	"os/signal"
	"strings"
	"syscall"
	"time"
)

//go:embed web/*
var files embed.FS

type Page struct {
	StoreURL, DeployDocs, Org, Space, Agent, Market, Gateway, Hub, HubMCP, MarketMCP string
	NativeMemory, CredentialStore, HubEnabled                                        bool
}

func pageFromEnv() Page {
	return Page{StoreURL: os.Getenv("GUIDE_STORE_URL"), DeployDocs: os.Getenv("GUIDE_DEPLOY_DOC_URL"), NativeMemory: os.Getenv("GUIDE_NATIVE_MEMORY") == "true", CredentialStore: os.Getenv("GUIDE_CREDENTIAL_STORE") == "true", Org: os.Getenv("GUIDE_ORG"), Space: os.Getenv("GUIDE_SPACE"), Agent: os.Getenv("GUIDE_AGENT_URL"), Market: os.Getenv("GUIDE_MARKET_URL"), Gateway: os.Getenv("GUIDE_GATEWAY_URL"), Hub: os.Getenv("GUIDE_HUB_URL"), HubMCP: os.Getenv("GUIDE_HUB_MCP_URL"), MarketMCP: os.Getenv("GUIDE_MARKET_MCP_URL"), HubEnabled: os.Getenv("GUIDE_HUB") == "true"}
}
func asset(name string) []byte {
	b, err := files.ReadFile(name)
	if err != nil {
		panic(err)
	}
	return b
}
func proxyEnv(c credential) []string {
	cookie := sha256.Sum256([]byte(c.Secret + ":northstar-guide-v1"))
	env := []string{"OAUTH2_PROXY_CLIENT_ID=" + c.ID, "OAUTH2_PROXY_CLIENT_SECRET=" + c.Secret, "OAUTH2_PROXY_COOKIE_SECRET=" + base64.RawURLEncoding.EncodeToString(cookie[:])}
	for _, key := range []string{"PATH", "HOME", "TMPDIR", "SSL_CERT_FILE", "SSL_CERT_DIR"} {
		if v := os.Getenv(key); v != "" {
			env = append(env, key+"="+v)
		}
	}
	return env
}
func handler(p Page) http.Handler {
	t := template.Must(template.ParseFS(files, "web/index.html"))
	css, js := asset("web/style.css"), asset("web/guide.js")
	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) { w.Write([]byte("ok")) })
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.Header().Set("Cache-Control", "no-store")
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("Referrer-Policy", "no-referrer")
		w.Header().Set("Content-Security-Policy", "default-src 'none'; img-src 'self'; style-src 'self'; script-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
		if err := t.Execute(w, p); err != nil {
			log.Print("template rendering failed")
		}
	})
	mux.HandleFunc("/style.css", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/css")
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Write(css)
	})
	mux.HandleFunc("/guide.js", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/javascript")
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Write(js)
	})
	mux.HandleFunc("/architecture.svg", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "image/svg+xml")
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("Content-Security-Policy", "default-src 'none'; style-src 'none'; sandbox")
		w.Write(asset("web/architecture.svg"))
	})
	return mux
}

type credential struct {
	Domain string `json:"auth_domain"`
	ID     string `json:"client_id"`
	Secret string `json:"client_secret"`
}

func sso(raw string) (credential, error) {
	var bindings map[string][]struct {
		Credentials credential `json:"credentials"`
	}
	if json.Unmarshal([]byte(raw), &bindings) != nil || len(bindings["p-identity"]) != 1 {
		return credential{}, errors.New("exactly one p-identity binding is required")
	}
	c := bindings["p-identity"][0].Credentials
	if !httpsURL(c.Domain) || c.ID == "" || c.Secret == "" {
		return credential{}, errors.New("invalid SSO binding")
	}
	return c, nil
}
func httpsURL(s string) bool {
	u, e := url.Parse(s)
	return e == nil && u.Scheme == "https" && u.Host != "" && u.User == nil && u.RawQuery == "" && u.Fragment == ""
}
func emailArgs(value string) ([]string, func(), error) {
	if value == "*" {
		return []string{"--email-domain=*"}, func() {}, nil
	}
	emails := strings.Split(value, ",")
	for i, e := range emails {
		e = strings.TrimSpace(e)
		a, err := mail.ParseAddress(e)
		if err != nil || a.Address != e || strings.ContainsAny(e, "*?\r\n") {
			return nil, func() {}, errors.New("explicit allowed emails required")
		}
		emails[i] = strings.ToLower(e)
	}
	f, err := os.CreateTemp("", "guide-emails-*")
	if err != nil {
		return nil, func() {}, err
	}
	cleanup := func() { os.Remove(f.Name()) }
	if _, err = f.WriteString(strings.Join(emails, "\n") + "\n"); err != nil {
		f.Close()
		cleanup()
		return nil, func() {}, err
	}
	f.Close()
	return []string{"--authenticated-emails-file=" + f.Name()}, cleanup, nil
}
func run(preview bool) error {
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer stop()
	p := pageFromEnv()
	listen := "127.0.0.1:8092"
	if preview {
		listen = "127.0.0.1:8766"
	}
	var cmd *exec.Cmd
	cleanup := func() {}
	if !preview {
		c, err := sso(os.Getenv("VCAP_SERVICES"))
		if err != nil {
			return err
		}
		base := os.Getenv("GUIDE_BASE_URL")
		if !httpsURL(base) {
			return errors.New("GUIDE_BASE_URL must be HTTPS")
		}
		port := os.Getenv("PORT")
		if port == "" {
			return errors.New("PORT required")
		}
		client := http.Client{Timeout: 15 * time.Second}
		resp, err := client.Get(strings.TrimRight(c.Domain, "/") + "/.well-known/openid-configuration")
		if err != nil {
			return errors.New("SSO discovery failed")
		}
		defer resp.Body.Close()
		var d struct {
			Issuer string `json:"issuer"`
			Login  string `json:"authorization_endpoint"`
			Token  string `json:"token_endpoint"`
			Keys   string `json:"jwks_uri"`
		}
		if resp.StatusCode != 200 || json.NewDecoder(http.MaxBytesReader(nil, resp.Body, 1<<20)).Decode(&d) != nil {
			return errors.New("invalid SSO discovery")
		}
		for _, u := range []string{d.Issuer, d.Login, d.Token, d.Keys} {
			if !httpsURL(u) {
				return errors.New("SSO endpoints must use HTTPS")
			}
		}
		emails, done, err := emailArgs(os.Getenv("APP_ALLOWED_EMAILS"))
		if err != nil {
			return err
		}
		cleanup = done
		defer cleanup()
		host, _ := url.Parse(base)
		args := []string{"--provider=oidc", "--skip-oidc-discovery=true", "--oidc-issuer-url=" + d.Issuer, "--login-url=" + d.Login, "--redeem-url=" + d.Token, "--oidc-jwks-url=" + d.Keys, "--skip-claims-from-profile-url=true", "--scope=" + strings.ReplaceAll(os.Getenv("SSO_SCOPES"), ",", " "), "--code-challenge-method=S256", "--redirect-url=" + strings.TrimRight(base, "/") + "/oauth2/callback", "--whitelist-domain=" + host.Host, "--http-address=0.0.0.0:" + port, "--upstream=http://" + listen, "--skip-provider-button=true", "--insecure-oidc-allow-unverified-email=" + fmt.Sprint(os.Getenv("SSO_ALLOW_UNVERIFIED_EMAIL") == "true"), "--cookie-name=__Host-northstar_guide", "--cookie-secure=true", "--cookie-httponly=true", "--cookie-samesite=lax", "--cookie-expire=8h", "--session-cookie-minimal=true", "--skip-auth-route=GET=^/health$", "--skip-auth-route=HEAD=^/health$", "--pass-basic-auth=false", "--pass-authorization-header=false", "--pass-access-token=false", "--request-logging=false", "--silence-ping-logging=true", "--banner=-", "--footer=-"}
		args = append(args, emails...)
		cmd = exec.Command("./oauth2-proxy", args...)
		cmd.Env = proxyEnv(c)
		cmd.Stdout = os.Stdout
		cmd.Stderr = os.Stderr
	}
	ln, err := net.Listen("tcp", listen)
	if err != nil {
		return err
	}
	server := &http.Server{Handler: handler(p), ReadHeaderTimeout: 5 * time.Second}
	defer server.Close()
	exits := make(chan error, 2)
	go func() { exits <- server.Serve(ln) }()
	if cmd != nil {
		if err := cmd.Start(); err != nil {
			return err
		}
		defer func() { _ = cmd.Process.Kill() }()
		go func() { exits <- cmd.Wait() }()
	}
	log.Print("Northstar guide ready")
	select {
	case <-ctx.Done():
		return nil
	case err := <-exits:
		if err == nil {
			return errors.New("guide child exited")
		}
		return err
	}
}
func main() {
	preview := flag.Bool("preview", false, "serve a local-only preview without authentication")
	flag.Parse()
	if *preview && os.Getenv("VCAP_APPLICATION") != "" {
		log.Fatal("preview is forbidden on Cloud Foundry")
	}
	if err := run(*preview); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
