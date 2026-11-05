import tempfile
import unittest
from pathlib import Path


def make_pdf(path,text):
    stream=f'BT /F1 12 Tf 20 100 Td ({text}) Tj ET'.encode()
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream']
    data=b'%PDF-1.4\n';offsets=[0]
    for i,obj in enumerate(objects,1):
        offsets.append(len(data));data+=f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n'
    start=len(data);data+=b'xref\n0 6\n0000000000 65535 f \n'
    for offset in offsets[1:]:data+=f'{offset:010d} 00000 n \n'.encode()
    data+=f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode()
    path.write_bytes(data)


class LinkStatusTest(unittest.TestCase):
    def test_success_requires_pdf_token_and_settings_change_invalidates_it(self):
        import mop_bridge as bridge
        self.assertTrue(hasattr(bridge,'confirm_test_pdf'),'연결 시험 증빙 필요')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);pdf=root/'test.pdf';proof=root/'link.json'
            config={'inbox':str(root),'printer':'PS TEST','executable':str(root/'mop.exe')}
            make_pdf(pdf,'KFTC-LINK-TEST')
            bridge.confirm_test_pdf(config,pdf,'KFTC-LINK-TEST',proof)
            self.assertIn('시험 성공',bridge.link_status(config,proof))
            other=dict(config,inbox=str(root/'changed'))
            self.assertIn('재시험',bridge.link_status(other,proof))

    def test_wrong_pdf_cannot_create_success_badge(self):
        import mop_bridge as bridge
        self.assertTrue(hasattr(bridge,'confirm_test_pdf'),'연결 시험 증빙 필요')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);pdf=root/'wrong.pdf';proof=root/'link.json'
            make_pdf(pdf,'WRONG-TOKEN')
            with self.assertRaises(ValueError):bridge.confirm_test_pdf({'inbox':td},pdf,'KFTC-LINK-TEST',proof)
            self.assertFalse(proof.exists())


if __name__=='__main__':unittest.main()
