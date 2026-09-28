package service

import (
	"testing"

	"ragflow/internal/entity"
)

func TestTeamModelAccessRequiresAcceptedMembership(t *testing.T) {
	for _, tt := range []struct {
		name   string
		role   string
		status string
		want   bool
	}{
		{name: "accepted member", role: "normal", status: "1", want: true},
		{name: "owner", role: "owner", status: "1", want: true},
		{name: "pending invitation", role: "invite", status: "1"},
		{name: "removed member", role: "normal", status: "0"},
		{name: "unrelated user"},
	} {
		t.Run(tt.name, func(t *testing.T) {
			db := setupModelProviderServiceTestDB(t)
			useModelProviderServiceTestDB(t, db)
			if tt.role != "" {
				if err := db.Create(&entity.UserTenant{ID: "membership", UserID: "member", TenantID: "owner", Role: tt.role, Status: &tt.status}).Error; err != nil {
					t.Fatal(err)
				}
			}
			allowed, err := NewModelProviderService().tenantCanReachProviderTenant(t.Context(), "member", "owner")
			if err != nil || allowed != tt.want {
				t.Fatalf("allowed=%v, error=%v; want %v", allowed, err, tt.want)
			}
		})
	}
}
