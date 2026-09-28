package handler

import (
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"

	"ragflow/internal/common"
	"ragflow/internal/dao"
)

// ModelTenantScope validates the team selected for model configuration and use.
// Configuration and credential endpoints require the team's owner role.
func ModelTenantScope(manage bool) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := c.GetString("user_id")
		if userID == "" {
			common.ErrorWithCode(c, common.CodeUnauthorized, "Unauthorized")
			c.Abort()
			return
		}
		tenantID := strings.TrimSpace(c.GetHeader("X-Model-Tenant"))
		// A user's own resources use the selected team; shared resources keep their owner scope.
		if c.Request.Method == http.MethodGet && c.FullPath() == "/api/v1/models" {
			if ownerID := c.Query("owner_tenant_id"); ownerID != "" && ownerID != userID {
				tenantID = ownerID
			}
		}
		if tenantID == "" {
			tenantID = userID
		}
		relation, err := dao.NewUserTenantDAO().FilterByUserIDAndTenantID(c.Request.Context(), dao.DB, userID, tenantID)
		if err != nil && !dao.IsNotFoundErr(err) {
			common.ErrorWithCode(c, common.CodeServerError, "Failed to check model team membership")
			c.Abort()
			return
		}
		if relation == nil || (relation.Role != "owner" && relation.Role != "normal") || (manage && relation.Role != "owner") {
			common.ResponseWithHttpCodeData(c, http.StatusForbidden, common.CodeAuthenticationError, nil, "Only team owners can manage model configuration; accepted members can use team models")
			c.Abort()
			return
		}
		c.Set("model_tenant_id", tenantID)
		c.Next()
	}
}

func modelTenantID(c *gin.Context) string {
	if tenantID := c.GetString("model_tenant_id"); tenantID != "" {
		return tenantID
	}
	return c.GetString("user_id")
}
