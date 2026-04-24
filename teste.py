import google.generativeai as genai

# Coloque sua chave aqui
genai.configure(api_key="AIzaSyD7YlninUL_tS1jgBNiX-xKn9eBVQG3M3E")

print("Listando modelos disponíveis...")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(m.name)