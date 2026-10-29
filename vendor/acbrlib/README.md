# ACBrLib NFe (Linux Console MT)

Artefatos necessários ao worker `acbr-lib` (Docker).

| Caminho | Origem |
|---------|--------|
| `Linux/CONSOLE-MT/libacbrnfe64.so` | Pacote Demo/Pro ACBrLibNFe Linux |
| `Schemas/NFe/` | `dep/Schemas/NFe` do mesmo pacote |
| `ACBrNFeServicos.ini` | `dep/ACBrNFeServicos.ini` |
| `openssl-legacy.cnf` | Receita Docker ACBr (OpenSSL 3 + legacy) |

Extraído de `downloads_acbrlib-demos/ACBrLibNFeDemo-Linux-*.7z`.

**Demo:** só homologação e ~30 min por processo (depois `-999 Demo expirou`).
O worker recicla sozinho; para produção contínua use a SO **Pro** (ACBr Pro).
