package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"net/http"
	"os"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/aws/session"
	"github.com/aws/aws-sdk-go/service/sns"
)

// Configurações
var (
	modelName   = "ft:gpt-4.1-mini-2025-04-14:aiko:webhooks-mini:C9i3m2e7"
	topicArn    = "arn:aws:sns:us-east-1:000000000000:CB-SPI_IUGU-MANUAL-HOOK-PIX-PAID_SENT"
	numWebhooks = 1
	apiKey      = os.Getenv("OPENAI_API_KEY")
)

// Estrutura para chamadas da API OpenAI
type ChatMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type ChatRequest struct {
	Model    string        `json:"model"`
	Messages []ChatMessage `json:"messages"`
}

type Choice struct {
	Message ChatMessage `json:"message"`
}

type ChatResponse struct {
	Choices []Choice `json:"choices"`
}

func generateWebhook(prompt string) (string, error) {
	url := "https://api.openai.com/v1/chat/completions"

	reqBody := ChatRequest{
		Model: modelName,
		Messages: []ChatMessage{
			{Role: "system", Content: "Você é um simulador de webhooks de Pix. Gere os eventos com IDs e valores fictícios."},
			{Role: "user", Content: prompt},
		},
	}

	jsonBody, err := json.Marshal(reqBody)
	if err != nil {
		return "", err
	}

	req, err := http.NewRequest("POST", url, bytes.NewBuffer(jsonBody))
	if err != nil {
		return "", err
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+apiKey)

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	bodyBytes, _ := ioutil.ReadAll(resp.Body)

	var chatResp ChatResponse
	if err := json.Unmarshal(bodyBytes, &chatResp); err != nil {
		return "", err
	}

	if len(chatResp.Choices) == 0 {
		return "", fmt.Errorf("nenhuma resposta recebida do modelo")
	}

	return chatResp.Choices[0].Message.Content, nil
}

func publishWebhookToSNS(webhookText string) error {
	// Criar sessão AWS
	sess, err := session.NewSession(&aws.Config{
		Region: aws.String("us-east-1"),
	})
	if err != nil {
		return fmt.Errorf("erro ao criar sessão AWS: %v", err)
	}

	// Criar cliente SNS
	snsClient := sns.New(sess)

	// Publicar mensagem no tópico
	input := &sns.PublishInput{
		TopicArn: aws.String(topicArn),
		Message:  aws.String(webhookText),
		Subject:  aws.String("Webhook PIX Simulado"),
	}

	result, err := snsClient.Publish(input)
	if err != nil {
		return fmt.Errorf("erro ao publicar no SNS: %v", err)
	}

	fmt.Printf("Webhook publicado no SNS! MessageId: %s\n", *result.MessageId)
	return nil
}

func main() {
	prompts := []string{
		"Simule um webhook de Pix Cash In de R$ 120",
		"Simule um webhook de Pix Cash Out de R$ 250",
		"Simule um webhook de Pix Cash In de R$ 500 pendente",
		"Simule um webhook de Pix Cash Out de R$ 300",
		"Simule um webhook de Pix Cash In de R$ 75",
	}

	for i := 0; i < numWebhooks; i++ {
		prompt := prompts[i%len(prompts)]
		webhookText, err := generateWebhook(prompt)
		if err != nil {
			fmt.Println("Erro ao gerar webhook:", err)
			continue
		}

		fmt.Printf("\nWebhook gerado:\n%s\n\n", webhookText)

		if err := publishWebhookToSNS(webhookText); err != nil {
			fmt.Println("Erro ao publicar webhook no SNS:", err)
		}
	}
}
