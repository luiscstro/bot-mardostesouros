"""Dashboard web do Doflamingo: gerencia as frutas da planilha (adicionar em massa, editar status, remover).

Roda numa thread dentro do próprio processo do bot e usa o mesmo EstoqueCog (mesma conexão e mesmo lock).
Só sobe se a variável de ambiente DASHBOARD_SENHA estiver definida.

Variáveis de ambiente:
  DASHBOARD_SENHA   senha de acesso (obrigatória para ligar o dashboard)
  DASHBOARD_SECRET  chave para assinar o cookie de sessão (opcional; senão é derivada da senha)
  DASHBOARD_PORT    porta (padrão: PORT ou 8080)
"""
import hashlib
import hmac
import os
import secrets
import threading
import time

from flask import Flask, jsonify, request, session, redirect, Response

import sys

MAX_TENTATIVAS = 5          # falhas de login por IP antes de bloquear
BLOQUEIO_SEGUNDOS = 300


def criar_app(cog, senha, secret=None):
    # Nomes vêm do módulo do próprio cog: importar "main" aqui recarregaria o bot quando ele roda como __main__.
    m = sys.modules[type(cog).__module__]
    RANKS, MAX_FRUTAS_POR_LOTE, parse_lote = m.RANKS, m.MAX_FRUTAS_POR_LOTE, m.parse_lote
    ErroPlanilha, PlanilhaIndisponivel = m.ErroPlanilha, m.PlanilhaIndisponivel
    app = Flask(__name__)
    app.secret_key = secret or hashlib.sha256(("doffy-dashboard:" + senha).encode()).hexdigest()
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=12 * 3600,
        MAX_CONTENT_LENGTH=256 * 1024,
    )
    falhas = {}  # ip -> (qtd, bloqueado_ate)

    @app.after_request
    def cabecalhos(resp):
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
            "connect-src 'self'; frame-ancestors 'none'; form-action 'self'")
        return resp

    def logado():
        return session.get("ok") is True

    def api(f):
        """Exige login e, nos POST, o token CSRF."""
        def wrapper(*a, **kw):
            if not logado():
                return jsonify(erro="Sessão expirada. Recarregue a página e entre de novo."), 401
            if request.method == "POST":
                if not hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), session.get("csrf", "x")):
                    return jsonify(erro="Token inválido. Recarregue a página."), 403
            try:
                return f(*a, **kw)
            except ErroPlanilha as e:
                return jsonify(erro=str(e)), 409
            except PlanilhaIndisponivel as e:
                print(f"❌ Dashboard: planilha indisponível: {e}")
                return jsonify(erro="Não consegui ler a planilha agora. Tente de novo em instantes."), 503
        wrapper.__name__ = f.__name__
        return wrapper

    # ---------------------------------------------------------------- páginas ---
    @app.get("/")
    def home():
        if not logado():
            return Response(PAGINA_LOGIN.replace("__ERRO__", ""), mimetype="text/html")
        return Response(PAGINA.replace("__CSRF__", session["csrf"]), mimetype="text/html")

    @app.post("/login")
    def login():
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()
        qtd, ate = falhas.get(ip, (0, 0))
        if ate > time.time():
            return Response(PAGINA_LOGIN.replace("__ERRO__", "Muitas tentativas. Aguarde alguns minutos."),
                            status=429, mimetype="text/html")
        if hmac.compare_digest(request.form.get("senha", "").encode(), senha.encode()):
            falhas.pop(ip, None)
            session.clear()
            session.permanent = True
            session["ok"] = True
            session["csrf"] = secrets.token_hex(16)
            return redirect("/")
        qtd += 1
        falhas[ip] = (qtd, time.time() + BLOQUEIO_SEGUNDOS if qtd >= MAX_TENTATIVAS else 0)
        return Response(PAGINA_LOGIN.replace("__ERRO__", "Senha incorreta."), status=401, mimetype="text/html")

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect("/")

    # -------------------------------------------------------------------- API ---
    @app.get("/api/frutas")
    @api
    def listar():
        t = cog._tabela_sync()
        frutas = [{k: f[k] for k in ("linha", "rank", "numero", "nome", "status")} for f in t["frutas"]]
        invalidas = [f for f in frutas if f["rank"] not in RANKS]
        return jsonify(frutas=frutas, invalidas=len(invalidas), ranks=list(RANKS))

    @app.post("/api/lote/previa")
    @api
    def previa():
        d = request.get_json(silent=True) or {}
        itens, erros = parse_lote(str(d.get("texto", "")), d.get("rank_padrao") or None)
        return jsonify(itens=itens[:MAX_FRUTAS_POR_LOTE + 1], erros=erros[:20], total=len(itens))

    @app.post("/api/lote")
    @api
    def lote():
        d = request.get_json(silent=True) or {}
        itens, erros = parse_lote(str(d.get("texto", "")), d.get("rank_padrao") or None)
        if erros:
            return jsonify(erro="Corrija antes de salvar: " + "; ".join(erros[:5])), 400
        if not itens:
            return jsonify(erro="Nenhuma fruta informada."), 400
        if len(itens) > MAX_FRUTAS_POR_LOTE:
            return jsonify(erro=f"Máximo de {MAX_FRUTAS_POR_LOTE} frutas por vez."), 400
        return jsonify(cog.adicionar_sync(itens))

    @app.post("/api/editar")
    @api
    def editar():
        d = request.get_json(silent=True) or {}
        try:
            linha = int(d.get("linha"))
        except (TypeError, ValueError):
            return jsonify(erro="Linha inválida."), 400
        nome = d.get("nome")
        status = d.get("status")
        cog.editar_sync(linha, str(d.get("nome_atual", "")),
                        nome=None if nome is None else str(nome),
                        status=None if status is None else str(status)[:200])
        return jsonify(ok=True)

    @app.post("/api/remover")
    @api
    def remover():
        d = request.get_json(silent=True) or {}
        try:
            linha = int(d.get("linha"))
        except (TypeError, ValueError):
            return jsonify(erro="Linha inválida."), 400
        f = cog.remover_sync(linha, str(d.get("nome", "")))
        return jsonify(ok=True, nome=f["nome"])

    return app


def iniciar_dashboard(cog):
    """Sobe o servidor numa thread daemon. Retorna o servidor, ou None se desligado/erro."""
    senha = os.getenv("DASHBOARD_SENHA", "")
    if not senha:
        print("ℹ️ Dashboard desligado (defina DASHBOARD_SENHA para ligar).")
        return None
    if cog is None:
        print("❌ Dashboard não iniciado: planilha (EstoqueCog) indisponível.")
        return None
    from werkzeug.serving import make_server
    porta = int(os.getenv("DASHBOARD_PORT") or os.getenv("PORT") or 8080)
    servidor = make_server("0.0.0.0", porta, criar_app(cog, senha, os.getenv("DASHBOARD_SECRET")), threaded=True)
    threading.Thread(target=servidor.serve_forever, name="dashboard", daemon=True).start()
    print(f"✅ Dashboard no ar na porta {porta}")
    return servidor


# ====================================================================== HTML ===
ESTILO = """
:root{--bg:#14121a;--card:#1e1b27;--card2:#262233;--txt:#ece9f5;--mut:#9a94ad;--bd:#332e44;--acc:#a78bfa;
--C:#57f287;--B:#3498db;--A:#e74c3c;--S:#9b59b6;--ok:#57f287;--err:#ff6b6b}
@media (prefers-color-scheme:light){:root{--bg:#f4f2fa;--card:#fff;--card2:#efecf8;--txt:#1d1a28;--mut:#6b6580;--bd:#ddd8ec;--acc:#6d4fd8}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.45 system-ui,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:16px}
button,input,select,textarea{font:inherit;color:inherit}
button{background:var(--acc);color:#fff;border:0;border-radius:8px;padding:8px 14px;cursor:pointer;font-weight:600}
button.sec{background:var(--card2);color:var(--txt);border:1px solid var(--bd)}
button.danger{background:transparent;color:var(--err);border:1px solid var(--err);padding:5px 10px}
button:disabled{opacity:.5;cursor:default}
input,select,textarea{background:var(--card2);border:1px solid var(--bd);border-radius:8px;padding:8px 10px;width:100%}
"""

PAGINA_LOGIN = """<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Doffy - Entrar</title>
<style>""" + ESTILO + """
.box{max-width:340px;margin:18vh auto;background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:24px}
h1{margin:0 0 16px;font-size:20px}.e{color:var(--err);min-height:1.3em;margin:8px 0}
</style></head><body><form class="box" method="post" action="/login">
<h1>🦩 Painel do Doflamingo</h1>
<input type="password" name="senha" placeholder="Senha" autofocus required>
<div class="e">__ERRO__</div><button style="width:100%">Entrar</button></form></body></html>"""

PAGINA = """<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Doffy - Frutas</title>
<style>""" + ESTILO + """
header{display:flex;align-items:center;gap:12px;justify-content:space-between;margin-bottom:14px}
h1{margin:0;font-size:20px}h2{margin:0 0 10px;font-size:16px}
.card{background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:16px;margin-bottom:16px}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.grow{flex:1;min-width:160px}
textarea{min-height:130px;resize:vertical;font-family:ui-monospace,Consolas,monospace;font-size:14px}
.hint{color:var(--mut);font-size:13px;margin:6px 0 10px}
.tabs{display:flex;gap:6px;flex-wrap:wrap}
.tab{background:var(--card2);color:var(--txt);border:1px solid var(--bd);padding:6px 12px;border-radius:999px}
.tab.on{background:var(--acc);color:#fff;border-color:var(--acc)}
table{width:100%;border-collapse:collapse;margin-top:12px}
th,td{text-align:left;padding:8px 6px;border-bottom:1px solid var(--bd);vertical-align:middle}
th{color:var(--mut);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.badge{display:inline-block;min-width:28px;text-align:center;padding:2px 8px;border-radius:6px;font-weight:700;color:#fff}
.C{background:var(--C);color:#0b2a14}.B{background:var(--B)}.A{background:var(--A)}.S{background:var(--S)}.X{background:#777}
td input{padding:5px 8px}
.msg{padding:10px 12px;border-radius:8px;margin-top:10px;white-space:pre-wrap}
.msg.ok{background:rgba(87,242,135,.12);border:1px solid var(--ok)}
.msg.err{background:rgba(255,107,107,.12);border:1px solid var(--err)}
.aviso{background:rgba(255,200,60,.12);border:1px solid #e0b030;border-radius:8px;padding:10px 12px;margin-bottom:14px}
.free{color:var(--ok)}.nt{width:1%;white-space:nowrap}
@media (max-width:640px){.hide-m{display:none}}
</style></head><body><div class="wrap">
<header><h1>🦩 Frutas — Mar dos Tesouros</h1>
<div class="row"><button class="sec" id="btn-rec">↻ Atualizar</button>
<form method="post" action="/logout" style="margin:0"><button class="sec">Sair</button></form></div></header>

<div id="aviso" class="aviso" hidden></div>

<section class="card"><h2>➕ Adicionar frutas (em massa)</h2>
<div class="hint">Uma linha por rank (<code>S: Fruta 1, Fruta 2</code>) ou escolha um rank padrão e cole só os nomes (um por linha ou separados por vírgula).
Pode misturar ranks no mesmo envio. Nomes que já existem são ignorados; o número é gerado automaticamente.</div>
<textarea id="lote" placeholder="S: Mera Mera no Mi, Goro Goro no Mi&#10;A: Bara Bara no Mi&#10;B: Hana Hana no Mi&#10;C: Fruta Qualquer"></textarea>
<div class="row" style="margin-top:10px"><label>Rank padrão&nbsp;
<select id="rk-padrao" style="width:auto"><option value="">— nenhum —</option><option>C</option><option>B</option><option>A</option><option>S</option></select></label>
<span id="previa" class="hint grow" style="margin:0"></span>
<button id="btn-add" disabled>Adicionar à planilha</button></div>
<div id="res-add"></div></section>

<section class="card"><h2>📖 Frutas cadastradas</h2>
<div class="row"><div class="tabs" id="tabs"></div>
<input id="busca" class="grow" placeholder="Buscar por nome ou nº…" style="max-width:300px;margin-left:auto">
<label class="row" style="gap:6px"><input type="checkbox" id="so-livres" style="width:auto"> só disponíveis</label></div>
<table><thead><tr><th class="nt">Rank</th><th class="nt">Nº</th><th>Nome</th><th>Status (vazio = disponível)</th><th class="nt"></th></tr></thead>
<tbody id="corpo"></tbody></table><div id="vazio" class="hint" hidden>Nenhuma fruta encontrada.</div>
<div id="res-lista"></div></section></div>

<script>
const CSRF="__CSRF__";let frutas=[],rank="TODOS";
const $=id=>document.getElementById(id);
async function chamar(url,corpo){
  const r=await fetch(url,{method:corpo===undefined?"GET":"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":CSRF},
    body:corpo===undefined?undefined:JSON.stringify(corpo)});
  let d={};try{d=await r.json()}catch(e){}
  if(r.status===401){location.reload();}
  if(!r.ok)throw new Error(d.erro||("Erro "+r.status));
  return d;
}
function msg(el,tipo,texto){el.innerHTML="";const d=document.createElement("div");d.className="msg "+tipo;d.textContent=texto;el.appendChild(d);}
function el(tag,props,...filhos){const e=document.createElement(tag);Object.assign(e,props||{});filhos.forEach(f=>e.append(f));return e;}

async function carregar(){
  try{const d=await chamar("/api/frutas");frutas=d.frutas;
    const av=$("aviso");av.hidden=!d.invalidas;
    if(d.invalidas)av.textContent="⚠️ "+d.invalidas+" linha(s) da planilha têm rank inválido (fora de C/B/A/S) e não aparecem no bot. Veja a aba 'X' abaixo.";
    desenhar();}catch(e){msg($("res-lista"),"err",e.message);}
}
function desenhar(){
  const cont={TODOS:frutas.length};frutas.forEach(f=>{const k=["C","B","A","S"].includes(f.rank)?f.rank:"X";cont[k]=(cont[k]||0)+1;});
  const tabs=$("tabs");tabs.innerHTML="";
  ["TODOS","C","B","A","S"].concat(cont.X?["X"]:[]).forEach(k=>{
    const b=el("button",{className:"tab"+(rank===k?" on":""),onclick:()=>{rank=k;desenhar();}},(k==="X"?"Inválidos":k==="TODOS"?"Todas":"Rank "+k)+" ("+(cont[k]||0)+")");tabs.appendChild(b);});
  const q=$("busca").value.toLowerCase().replace(/\\s+/g,""),livres=$("so-livres").checked;
  const peso={C:1,B:2,A:3,S:4};
  const lista=frutas.filter(f=>{
    const k=["C","B","A","S"].includes(f.rank)?f.rank:"X";
    if(rank!=="TODOS"&&k!==rank)return false;
    if(livres&&f.status)return false;
    if(q&&!(f.nome.toLowerCase().replace(/\\s+/g,"").includes(q)||f.numero===q||(f.rank.toLowerCase()+f.numero)===q))return false;
    return true;
  }).sort((a,b)=>(peso[a.rank]||99)-(peso[b.rank]||99)||(parseInt(a.numero)||99999)-(parseInt(b.numero)||99999));
  const corpo=$("corpo");corpo.innerHTML="";$("vazio").hidden=lista.length>0;
  lista.forEach(f=>{
    const st=el("input",{value:f.status,placeholder:"disponível",maxLength:200});
    const salvar=async()=>{if(st.value.trim().toLowerCase()===f.status)return;
      try{await chamar("/api/editar",{linha:f.linha,nome_atual:f.nome,status:st.value});f.status=st.value.trim().toLowerCase();
        msg($("res-lista"),"ok","Status de "+f.nome+" atualizado.");}catch(e){msg($("res-lista"),"err",e.message);carregar();}};
    st.addEventListener("change",salvar);st.addEventListener("keydown",e=>{if(e.key==="Enter")st.blur();});
    const nome=el("input",{value:f.nome,maxLength:100});
    nome.addEventListener("change",async()=>{try{await chamar("/api/editar",{linha:f.linha,nome_atual:f.nome,nome:nome.value});
      msg($("res-lista"),"ok","Nome alterado.");carregar();}catch(e){msg($("res-lista"),"err",e.message);carregar();}});
    const del=el("button",{className:"danger",title:"Remover da planilha",onclick:async()=>{
      if(!confirm("Remover "+f.nome+" da planilha? Isso apaga a linha."))return;
      try{await chamar("/api/remover",{linha:f.linha,nome:f.nome});msg($("res-lista"),"ok",f.nome+" removida.");carregar();}
      catch(e){msg($("res-lista"),"err",e.message);carregar();}}},"Remover");
    const k=["C","B","A","S"].includes(f.rank)?f.rank:"X";
    corpo.appendChild(el("tr",null,el("td",{className:"nt"},el("span",{className:"badge "+k},f.rank||"?")),
      el("td",{className:"nt"},"#"+f.numero),el("td",null,nome),el("td",null,st),el("td",{className:"nt"},del)));
  });
}
let t=null;
async function atualizarPrevia(){
  const texto=$("lote").value;if(!texto.trim()){$("previa").textContent="";$("btn-add").disabled=true;return;}
  try{const d=await chamar("/api/lote/previa",{texto,rank_padrao:$("rk-padrao").value});
    const pr={};d.itens.forEach(i=>pr[i.rank]=(pr[i.rank]||0)+1);
    let s=d.total+" fruta(s): "+Object.entries(pr).map(([k,v])=>k+"="+v).join(", ");
    if(d.erros.length)s+="  ⚠️ "+d.erros.join("; ");
    $("previa").textContent=s;$("btn-add").disabled=!d.total||d.erros.length>0;}
  catch(e){$("previa").textContent=e.message;$("btn-add").disabled=true;}
}
["lote","rk-padrao"].forEach(id=>$(id).addEventListener("input",()=>{clearTimeout(t);t=setTimeout(atualizarPrevia,250);}));
$("btn-add").onclick=async()=>{
  $("btn-add").disabled=true;
  try{const r=await chamar("/api/lote",{texto:$("lote").value,rank_padrao:$("rk-padrao").value});
    let s=r.adicionadas.length+" fruta(s) adicionada(s)"+(r.adicionadas.length?":\\n"+r.adicionadas.map(f=>"• "+f.rank+"#"+f.numero+" "+f.nome).join("\\n"):"");
    if(r.duplicadas.length)s+="\\n\\nJá existiam (ignoradas): "+r.duplicadas.join(", ");
    if(r.rejeitadas.length)s+="\\n\\nRejeitadas:\\n"+r.rejeitadas.join("\\n");
    msg($("res-add"),r.adicionadas.length?"ok":"err",s);
    if(r.adicionadas.length){$("lote").value="";$("previa").textContent="";carregar();}
  }catch(e){msg($("res-add"),"err",e.message);$("btn-add").disabled=false;}
};
$("busca").addEventListener("input",desenhar);$("so-livres").addEventListener("change",desenhar);$("btn-rec").onclick=carregar;
carregar();
</script></body></html>"""
