import express from "express";
import fetch from "node-fetch";
import OpenAI from "openai";

const app = express();
app.use(express.json());

const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

// endpoint para gerar e disparar webhook fake
app.post("/simulate", async (req, res) => {
  const { scenario, targetUrl } = req.body;

  // exemplos reais de webhook (você coloca alguns aqui)
  const examples = [
    {
      type: "cashin",
      payload: {
        id: "123",
        type: "cashin",
        amount: 1000,
        currency: "BRL",
        status: "confirmed",
        createdAt: "2025-08-27T12:00:00Z"
      }
    },
    {
      type: "cashout",
      payload: {
        id: "999",
        type: "cashout",
        amount: 500,
        currency: "BRL",
        status: "pending",
        createdAt: "2025-08-27T13:00:00Z"
      }
    }
  ];

  // pedir ao modelo para gerar payload novo baseado nos exemplos
  const completion = await openai.chat.completions.create({
    model: "gpt-4o-mini", // pode trocar para mais barato/rápido
    messages: [
      { role: "system", content: "Você é um simulador de webhooks de pagamentos." },
      { role: "user", content: `Aqui estão exemplos de webhooks:\n${JSON.stringify(examples, null, 2)}` },
      { role: "user", content: `Gere um webhook no mesmo formato para o seguinte cenário: ${scenario}. Apenas retorne JSON válido.` }
    ],
    temperature: 0.2
  });

  const jsonStr = completion.choices[0].message.content;
  let payload;
  try {
    payload = JSON.parse(jsonStr);
  } catch (e) {
    return res.status(500).json({ error: "Erro ao parsear JSON da IA", raw: jsonStr });
  }

  // dispara para o serviço local como se fosse o parceiro
  await fetch(targetUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });

  res.json({ message: "Webhook simulado enviado!", payload });
});

app.listen(3001, () => console.log("Simulador rodando em http://localhost:3001"));
