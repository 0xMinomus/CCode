import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'services/voice'))
from terminology import normalize_terms
class VoiceTermsTests(unittest.TestCase):
 def test_requested_technical_repair(self):self.assertEqual(normalize_terms('Pakai komputer rius lalu buka YouTube.'),'Pakai computer use lalu buka YouTube.')
 def test_preserves_normal_speech(self):
  for text in ['Komputer saya rusak.','My computer user account is locked.','Buka browser dan cari musik.']:self.assertEqual(normalize_terms(text),text)
