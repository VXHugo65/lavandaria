from django.test import TestCase
import requests

API_URL = 'http://api.mozesms.com/bulk_json/v2/'
BEARER_TOKEN = 'Bearer 2309:fI1aPs-MCF2CJ-nKkMQD-61cLGv'
SENDER = "ESHOP"

# Número de telefone no formato correto
telefone = '+258878750526'

mensagem = "Teste de envio de SMS via API Mozesms."

payload = {
    'sender': 'ESHOP',
    'messages': [{
        'number': telefone,
        'text': mensagem,
        'from': SENDER
    }]
}
headers = {'Authorization': BEARER_TOKEN}

response = requests.post(API_URL, json=payload, headers=headers)

print("Código de resposta:", response.status_code)
print("Resposta da API:", response.text)
