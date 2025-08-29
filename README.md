/// preparar jsonl se for open ai 3.5
openai tools fine_tunes.prepare_data -f webhooks.jsonl

/// upar fine tuning

openai api files.create -f "webhooks_gpt4_mini.jsonl" -p "fine-tune"

openai api fine_tuning.jobs.create \
  -m "gpt-4.1-mini-2025-04-14" \
  -F "file-DWXAvojZc4AUi1Xg8v5PvX" \
  -s "webhooks_mini"

// verificar fine tuning
openai api fine_tuning.jobs.retrieve -i ftjob-UUR3fTdxo8B0GYqWaHVjomeM

// chamar fine tuning
  1️⃣ Usando a API via CLI com completions.create
openai api completions.create \
  -m "ft-webhooks" \
  -p "Simule um webhook de Pix Cash In no valor de R$ 100,00." \
  -M 500
-m "ft-webhooks" → nome do seu modelo fine-tunado (ft-XXXX ou o sufixo que você deu)
-p → prompt descrevendo o webhook que quer gerar
-M 500 → máximo de tokens para a resposta