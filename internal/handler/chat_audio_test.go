package handler

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/glebarez/sqlite"
	"gorm.io/gorm"

	"ragflow/internal/common"
	"ragflow/internal/dao"
	"ragflow/internal/entity"
	"ragflow/internal/service"
)

// The chat TTS response may carry model/driver context but never the provider's
// raw error body; the full synthesis error stays in the server-side log.
func TestChatAudioSpeechFailureOmitsProviderError(t *testing.T) {
	providerBody := `{"code":20052,"message":"Voice or reference audio should be set","request_id":"secret-internal-diagnostic"}`
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
		_, _ = w.Write([]byte(providerBody))
	}))
	defer server.Close()

	prevAllow := common.AllowAnyHostForTest
	common.AllowAnyHostForTest = true
	t.Cleanup(func() { common.AllowAnyHostForTest = prevAllow })

	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{TranslateError: true})
	if err != nil {
		t.Fatalf("failed to open sqlite: %v", err)
	}
	if err = db.AutoMigrate(
		&entity.Tenant{},
		&entity.UserTenant{},
		&entity.TenantModel{},
		&entity.TenantModelProvider{},
		&entity.TenantModelInstance{},
	); err != nil {
		t.Fatalf("failed to migrate test schema: %v", err)
	}
	origDB := dao.DB
	dao.DB = db
	t.Cleanup(func() { dao.DB = origDB })

	tenantName := "tts-test-tenant"
	ttsModelID := "tm-tts-1"
	if err = db.Create(&entity.Tenant{
		ID:        "team-1",
		Name:      &tenantName,
		TTSID:     &ttsModelID,
		ParserIDs: "naive",
	}).Error; err != nil {
		t.Fatalf("failed to create tenant: %v", err)
	}
	if err = db.Create(&entity.TenantModel{
		ID:         ttsModelID,
		ModelName:  "FunAudioLLM/CosyVoice2-0.5B",
		ProviderID: "prov-1",
		InstanceID: "inst-1",
		ModelType:  int(entity.ModelTypeTTS),
		Status:     "active",
		Extra:      "{}",
	}).Error; err != nil {
		t.Fatalf("failed to create tenant model: %v", err)
	}
	if err = db.Create(&entity.TenantModelProvider{
		ID:           "prov-1",
		ProviderName: "SILICONFLOW",
		TenantID:     "team-1",
	}).Error; err != nil {
		t.Fatalf("failed to create provider: %v", err)
	}
	if err = db.Create(&entity.TenantModelInstance{
		ID:           "inst-1",
		InstanceName: "default",
		ProviderID:   "prov-1",
		APIKey:       "test-key",
		Status:       "active",
		Extra:        fmt.Sprintf(`{"base_url":%q}`, server.URL),
	}).Error; err != nil {
		t.Fatalf("failed to create instance: %v", err)
	}

	// The actor has no personal TTS default; synthesis must use the selected team.
	active := "1"
	if err := db.Create(&entity.UserTenant{ID: "membership", UserID: "user-1", TenantID: "team-1", Role: "normal", Status: &active}).Error; err != nil {
		t.Fatal(err)
	}

	h := NewChatHandler(service.NewChatService(), service.NewUserService())
	h.SetMindMapDependencies(nil, nil, service.NewModelProviderService(), nil)

	c, w := setupGinContextWithUser(http.MethodPost, "/api/v1/chat/audio/speech", `{"text":"hello"}`)
	c.Request.Header.Set("X-Model-Tenant", "team-1")
	router := gin.New()
	router.Use(func(requestContext *gin.Context) {
		requestContext.Set("user", c.MustGet("user"))
		requestContext.Set("user_id", "user-1")
	})
	router.POST("/api/v1/chat/audio/speech", ModelTenantScope(false), h.ChatAudioSpeech)
	router.ServeHTTP(w, c.Request)

	body := w.Body.String()
	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to decode response: %v (body=%s)", err, body)
	}
	if resp["code"] != float64(common.CodeServerError) {
		t.Fatalf("code = %v, want %d (body=%s)", resp["code"], common.CodeServerError, body)
	}
	if !strings.Contains(body, "TTS synthesis failed for model FunAudioLLM/CosyVoice2-0.5B (SILICONFLOW)") {
		t.Fatalf("response missing model/driver context: %s", body)
	}
	if strings.Contains(body, "secret-internal-diagnostic") || strings.Contains(body, "SiliconFlow TTS API error") {
		t.Fatalf("response leaks provider error detail: %s", body)
	}
}
