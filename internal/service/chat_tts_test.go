package service

import (
	"testing"

	"ragflow/internal/entity"
)

func TestChatTTSUsesSavedTeamModel(t *testing.T) {
	db := setupModelProviderServiceTestDB(t)
	useModelProviderServiceTestDB(t, db)
	active := "1"
	for _, row := range []interface{}{
		&entity.UserTenant{ID: "membership", UserID: "member", TenantID: "team", Role: "normal", Status: &active},
		&entity.TenantModelProvider{ID: "provider", TenantID: "team", ProviderName: "SILICONFLOW"},
		&entity.TenantModelInstance{ID: "instance", ProviderID: "provider", InstanceName: "default", APIKey: "team-key", Status: "active", Extra: "{}"},
		&entity.TenantModel{ID: "team-tts", ProviderID: "provider", InstanceID: "instance", ModelName: "FunAudioLLM/CosyVoice2-0.5B", ModelType: int(entity.ModelTypeTTS), Status: "active", Extra: "{}"},
	} {
		if err := db.Create(row).Error; err != nil {
			t.Fatal(err)
		}
	}
	chat := &entity.Chat{TenantID: "member", PromptConfig: map[string]interface{}{"tts": true, "tts_model_id": "team-tts"}}
	svc := NewChatPipelineService()
	target, err := svc.resolveChatTTSModel(t.Context(), chat)
	if err != nil {
		t.Fatal(err)
	}
	if target.ModelName != "FunAudioLLM/CosyVoice2-0.5B" || target.APIConfig.ApiKey == nil || *target.APIConfig.ApiKey != "team-key" {
		t.Fatal("TTS did not use the saved team's model and credentials")
	}
	for _, membership := range []map[string]interface{}{
		{"role": "invite", "status": "1"},
		{"role": "normal", "status": "0"},
	} {
		if err := db.Model(&entity.UserTenant{}).Where("id = ?", "membership").Updates(membership).Error; err != nil {
			t.Fatal(err)
		}
		if _, err := svc.resolveChatTTSModel(t.Context(), chat); err == nil {
			t.Fatalf("TTS resolved with invalid membership %v", membership)
		}
	}
}
