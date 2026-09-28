package handler

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"

	"ragflow/internal/entity"
)

func TestModelTenantScopePermissions(t *testing.T) {
	for _, tt := range []struct {
		name   string
		role   string
		status string
		manage bool
		want   int
	}{
		{name: "owner manages", role: "owner", status: "1", manage: true, want: http.StatusOK},
		{name: "member reads", role: "normal", status: "1", want: http.StatusOK},
		{name: "member cannot modify or read credentials", role: "normal", status: "1", manage: true, want: http.StatusForbidden},
		{name: "pending invitation", role: "invite", status: "1", want: http.StatusForbidden},
		{name: "removed member", role: "normal", status: "0", want: http.StatusForbidden},
		{name: "unrelated user", want: http.StatusForbidden},
	} {
		t.Run(tt.name, func(t *testing.T) {
			db := setupProviderHandlerTestDB(t)
			useProviderHandlerTestDB(t, db)
			if tt.role != "" {
				if err := db.Create(&entity.UserTenant{ID: "membership", UserID: "member", TenantID: "owner", Role: tt.role, Status: &tt.status}).Error; err != nil {
					t.Fatal(err)
				}
			}
			gin.SetMode(gin.TestMode)
			router := gin.New()
			router.Use(func(c *gin.Context) { c.Set("user_id", "member") })
			called := false
			router.GET("/api/v1/models/default", ModelTenantScope(tt.manage), func(c *gin.Context) {
				called = true
				if modelTenantID(c) != "owner" || c.GetString("user_id") != "member" {
					t.Fatalf("selected tenant = %q, actor = %q", modelTenantID(c), c.GetString("user_id"))
				}
				c.Status(http.StatusOK)
			})
			request := httptest.NewRequest(http.MethodGet, "/api/v1/models/default", nil)
			request.Header.Set("X-Model-Tenant", "owner")
			response := httptest.NewRecorder()
			router.ServeHTTP(response, request)
			if response.Code != tt.want || called != (tt.want == http.StatusOK) {
				t.Fatalf("status = %d, called = %v; want %d; body=%s", response.Code, called, tt.want, response.Body.String())
			}
		})
	}
}

func TestModelTenantScopeResourceOwner(t *testing.T) {
	db := setupProviderHandlerTestDB(t)
	useProviderHandlerTestDB(t, db)
	active := "1"
	for _, team := range []string{"member", "selected-team", "resource-owner"} {
		if err := db.Create(&entity.UserTenant{ID: team, UserID: "member", TenantID: team, Role: "normal", Status: &active}).Error; err != nil {
			t.Fatal(err)
		}
	}
	gin.SetMode(gin.TestMode)
	router := gin.New()
	router.Use(func(c *gin.Context) { c.Set("user_id", "member") })
	router.GET("/api/v1/models", ModelTenantScope(false), func(c *gin.Context) { c.String(http.StatusOK, modelTenantID(c)) })
	for _, tt := range []struct {
		owner string
		want  string
	}{
		{owner: "resource-owner", want: "resource-owner"},
		{owner: "member", want: "selected-team"},
	} {
		request := httptest.NewRequest(http.MethodGet, "/api/v1/models?owner_tenant_id="+tt.owner, nil)
		request.Header.Set("X-Model-Tenant", "selected-team")
		response := httptest.NewRecorder()
		router.ServeHTTP(response, request)
		if response.Code != http.StatusOK || response.Body.String() != tt.want {
			t.Fatalf("owner %q: status=%d body=%s, want %s", tt.owner, response.Code, response.Body.String(), tt.want)
		}
	}
	request := httptest.NewRequest(http.MethodGet, "/api/v1/models?owner_tenant_id=unrelated", nil)
	request.Header.Set("X-Model-Tenant", "selected-team")
	response := httptest.NewRecorder()
	router.ServeHTTP(response, request)
	if response.Code != http.StatusForbidden {
		t.Fatalf("unrelated resource owner status = %d", response.Code)
	}
}
