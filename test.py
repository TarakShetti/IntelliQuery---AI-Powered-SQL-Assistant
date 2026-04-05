import google.generativeai as genai

print("START")

genai.configure(api_key="YOUR_API_KEY_HERE")

model = genai.GenerativeModel("gemini-1.5-flash")

response = model.generate_content("Say hello in one line")

print("RESPONSE OBJECT:", response)

try:
    print("TEXT:", response.text)
except Exception as e:
    print("TEXT ERROR:", e)

print("END")