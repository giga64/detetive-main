"""Teste se Tesseract está funcionando"""
import pytesseract
from PIL import Image
import io

# Criar uma imagem de teste simples
img = Image.new('RGB', (200, 50), color='white')

try:
    texto = pytesseract.image_to_string(img, lang='por')
    print("✅ Tesseract funciona!")
    print(f"   Resultado: '{texto}'")
except Exception as e:
    print(f"❌ Erro no Tesseract: {e}")
    print("\n💡 Você precisa instalar o Tesseract:")
    print("   Windows: https://github.com/UB-Mannheim/tesseract/wiki")
    print("   Depois configure: pytesseract.pytesseract.tesseract_cmd = r'C:\\Program Files\\Tesseract-OCR\\tesseract.exe'")
