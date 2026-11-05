# ACBrLib NFe Pro (Linux Console MT)

Artefatos do worker `acbr-lib` (Docker). API ctypes igual à Demo; a SO Pro emite em homologação e produção, sem o limite de ~30 min.

| Caminho | Origem |
|---------|--------|
| `Linux/CONSOLE-MT/libacbrnfe64.so` | `acbrlibpro/ACBrLibNFe-Linux-1.5.0.493.7z` (Pro) |
| `Schemas/NFe/` | `dep/Schemas/NFe` do mesmo pacote |
| `ACBrNFeServicos.ini` | `dep/ACBrNFeServicos.ini` |
| `openssl-legacy.cnf` | Receita Docker ACBr (OpenSSL 3 + legacy) |

Consulta CNPJ: `Linux/CONSOLE-MT/libacbrconsultacnpj64.so` (mesmo pacote Pro). O worker chama essa SO em **subprocesso**, para não misturar com a NFe no Linux. NFS-e continua fora deste worker.
