"""
Real-time Dashboard for Geelark Instagram Automation
Run: python dashboard.py  |  Open: http://localhost:5000
"""
import os, json
from datetime import datetime
from flask import Flask, render_template_string, jsonify, request

app = Flask(__name__)
STATE_FILE = "scheduler_state.json"
LOG_FILE = "scheduler_live.log"

HTML = """
<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:sans-serif;background:#1a1a2e;color:#fff;min-height:100vh;padding:20px}
.container{max-width:1400px;margin:0 auto}
header{text-align:center;margin-bottom:20px;padding:15px;background:rgba(255,255,255,0.05);border-radius:10px}
h1{font-size:2em;color:#00d4ff}
.stats{display:flex;gap:15px;justify-content:center;margin-bottom:20px}
.stat{background:rgba(255,255,255,0.08);padding:20px 30px;border-radius:10px;text-align:center}
.stat h3{font-size:0.8em;color:#888;margin-bottom:5px}
.stat-val{font-size:2em;font-weight:bold}
.success{color:#00ff88}.error{color:#ff4757}.pending{color:#ffa502}.active{color:#00d4ff}
.main-grid{display:grid;grid-template-columns:350px 1fr;gap:20px}
.side-panels{display:flex;flex-direction:column;gap:20px}
.panel{background:rgba(255,255,255,0.05);border-radius:10px;padding:15px}
.panel h2{font-size:1em;color:#00d4ff;margin-bottom:10px;border-bottom:1px solid #333;padding-bottom:5px}
.acct{padding:10px;margin:5px 0;background:rgba(255,255,255,0.03);border-radius:5px;display:flex;align-items:center;border-left:3px solid #333}
.acct.success{border-left-color:#00ff88}.acct.in_progress{border-left-color:#00d4ff;background:rgba(0,212,255,0.1)}
.acct.pending{border-left-color:#666}.acct.failed{border-left-color:#ff4757}
.acct-name{flex:1;font-weight:bold}
.acct-status{font-size:0.8em;padding:3px 10px;border-radius:10px;background:rgba(255,255,255,0.1)}
.current{background:rgba(0,212,255,0.1);padding:10px;border-radius:5px;margin-bottom:10px}
.act{padding:8px;margin:3px 0;font-size:0.9em;background:rgba(255,255,255,0.02);border-radius:5px}
.time{color:#666;font-size:0.8em}
.icon{margin-right:8px}
#refresh{position:fixed;top:10px;right:10px;padding:5px 10px;background:rgba(0,212,255,0.2);border-radius:15px;font-size:0.8em;color:#00d4ff}
.log-panel{flex:1;display:flex;flex-direction:column;min-height:500px}
.log-panel h2{display:flex;justify-content:space-between;align-items:center}
.log-controls{display:flex;gap:10px}
.log-controls button{background:rgba(255,255,255,0.1);border:none;color:#888;padding:3px 8px;border-radius:5px;cursor:pointer;font-size:0.8em}
.log-controls button:hover{background:rgba(255,255,255,0.2);color:#fff}
.log-controls button.active{background:rgba(0,212,255,0.3);color:#00d4ff}
#log-container{flex:1;background:#0d0d1a;border-radius:5px;padding:10px;overflow-y:auto;font-family:'Consolas','Monaco',monospace;font-size:12px;line-height:1.5;max-height:600px}
.log-line{padding:2px 0;border-bottom:1px solid rgba(255,255,255,0.03)}
.log-ts{color:#666;margin-right:10px}
.log-msg{color:#ccc}
.log-line.highlight{background:rgba(0,212,255,0.1)}
.log-line.error{color:#ff4757}
.log-line.success{color:#00ff88}
</style></head>
<body><div class="container">
<header><h1>Instagram Automation Dashboard</h1><p id="last">Loading...</p></header>
<div class="stats">
<div class="stat"><h3>SUCCESS</h3><div class="stat-val success" id="s-ok">-</div></div>
<div class="stat"><h3>ACTIVE</h3><div class="stat-val active" id="s-act">-</div></div>
<div class="stat"><h3>PENDING</h3><div class="stat-val pending" id="s-pend">-</div></div>
<div class="stat"><h3>FAILED</h3><div class="stat-val error" id="s-fail">-</div></div>
</div>
<div class="main-grid">
<div class="side-panels">
<div class="panel"><h2>Account Status</h2><div id="current"></div><div id="accts"></div></div>
<div class="panel"><h2>Recent Activity</h2><div id="activity"></div></div>
</div>
<div class="panel log-panel">
<h2>Live Logs <div class="log-controls"><button id="btn-scroll" class="active" onclick="toggleScroll()">Auto-scroll</button><button onclick="clearLogs()">Clear</button></div></h2>
<div id="log-container"></div>
</div>
</div></div>
<div id="refresh">Auto-refresh: 2s</div>
<script>
var lastLogLine=0;
var autoScroll=true;

function toggleScroll(){
  autoScroll=!autoScroll;
  document.getElementById('btn-scroll').className=autoScroll?'active':'';
}

function clearLogs(){
  document.getElementById('log-container').innerHTML='';
  lastLogLine=0;
}

function escapeHtml(t){
  return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function updateStatus(){
  fetch('/api/status').then(r=>r.json()).then(d=>{
    document.getElementById('s-ok').textContent=d.stats.success;
    document.getElementById('s-act').textContent=d.stats.in_progress;
    document.getElementById('s-pend').textContent=d.stats.pending;
    document.getElementById('s-fail').textContent=d.stats.failed;
    var cj=document.getElementById('current');
    if(d.current_job){cj.innerHTML='<div class="current"><b>Now Posting:</b> '+d.current_job.account+' - '+d.current_job.id+'</div>';}
    else{cj.innerHTML='<div class="current">No active job</div>';}
    var al=document.getElementById('accts');
    al.innerHTML=d.accounts.map(a=>'<div class="acct '+a.status+'"><span class="icon">'+(a.status=='success'?'OK':a.status=='in_progress'?'>>':'--')+'</span><span class="acct-name">'+a.name+'</span><span class="acct-status">'+a.status+'</span></div>').join('');
    var af=document.getElementById('activity');
    af.innerHTML=d.recent_activity.map(a=>'<div class="act"><span class="time">'+a.time+'</span> <b>'+a.account+'</b>: '+a.status+(a.video?' ('+a.video+')':'')+'</div>').join('');
    document.getElementById('last').textContent='Updated: '+new Date().toLocaleTimeString();
  });
}

function updateLogs(){
  fetch('/api/logs?since='+lastLogLine).then(r=>r.json()).then(d=>{
    if(d.lines && d.lines.length>0){
      var container=document.getElementById('log-container');
      d.lines.forEach(function(line){
        var div=document.createElement('div');
        div.className='log-line';
        if(line.indexOf('[OK]')>-1||line.indexOf('SUCCESS')>-1) div.className+=' success';
        else if(line.indexOf('ERROR')>-1||line.indexOf('FAIL')>-1||line.indexOf('error')>-1) div.className+=' error';
        else if(line.indexOf('Step')>-1||line.indexOf('Posting')>-1) div.className+=' highlight';
        // Parse timestamp if present
        var match=line.match(/^\\[(\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2})\\]\\s*(.*)$/);
        if(match){
          div.innerHTML='<span class="log-ts">'+match[1].split(' ')[1]+'</span><span class="log-msg">'+escapeHtml(match[2])+'</span>';
        }else{
          div.innerHTML='<span class="log-msg">'+escapeHtml(line)+'</span>';
        }
        container.appendChild(div);
      });
      lastLogLine=d.last_line;
      if(autoScroll) container.scrollTop=container.scrollHeight;
    }
  });
}

updateStatus();
updateLogs();
setInterval(updateStatus,3000);
setInterval(updateLogs,1500);
</script></body></html>
"""

def load_state():
    if not os.path.exists(STATE_FILE): return {"jobs":[],"accounts":{}}
    try:
        with open(STATE_FILE,'r',encoding='utf-8') as f: return json.load(f)
    except: return {"jobs":[],"accounts":{}}

def get_stats(jobs):
    s={"success":0,"in_progress":0,"pending":0,"failed":0}
    for j in jobs:
        st=j.get('status','pending')
        if st in s: s[st]+=1
    return s

def get_accounts(jobs, accts):
    # accts is a list of dicts with 'name' field
    acc={}
    for a in accts:
        name = a.get('name','') if isinstance(a,dict) else a
        if name: acc[name]={"name":name,"status":"pending"}
    for j in jobs:
        a=j.get('account','')
        if not a: continue
        if a not in acc: acc[a]={"name":a,"status":"pending"}
        st=j.get('status','pending')
        if st=='in_progress': acc[a]["status"]="in_progress"
        elif st=='success' and acc[a]["status"]!="in_progress": acc[a]["status"]="success"
        elif st=='failed' and acc[a]["status"] not in["in_progress","success"]: acc[a]["status"]="failed"
    return list(acc.values())

def get_activity(jobs,limit=20):
    sj=sorted([j for j in jobs if j.get('last_attempt')or j.get('completed_at')],key=lambda x:x.get('completed_at')or x.get('last_attempt')or'',reverse=True)[:limit]
    act=[]
    for j in sj:
        t=j.get('completed_at')or j.get('last_attempt')or''
        if t:
            try: t=datetime.fromisoformat(t).strftime("%H:%M:%S")
            except: pass
        act.append({"time":t,"account":j.get('account','?'),"status":j.get('status','?'),"video":j.get('id','')})
    return act

def get_current(jobs):
    for j in jobs:
        if j.get('status')=='in_progress': return j
    return None

def get_log_lines(since=0, limit=500):
    """Read log lines from file starting at line number 'since'"""
    if not os.path.exists(LOG_FILE):
        return [], 0
    try:
        with open(LOG_FILE, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        # Return lines after 'since' index
        new_lines = [l.rstrip() for l in lines[since:since+limit] if l.strip()]
        return new_lines, len(lines)
    except:
        return [], 0

@app.route('/')
def index(): return render_template_string(HTML)

@app.route('/api/status')
def api_status():
    st=load_state()
    jobs=st.get('jobs',[])
    accts=st.get('accounts',{})
    return jsonify({"stats":get_stats(jobs),"accounts":get_accounts(jobs,accts),"recent_activity":get_activity(jobs),"current_job":get_current(jobs)})

@app.route('/api/logs')
def api_logs():
    since = request.args.get('since', 0, type=int)
    lines, total = get_log_lines(since)
    return jsonify({"lines": lines, "last_line": total, "since": since})

if __name__=='__main__':
    print("\n"+"="*50)
    print("  Instagram Automation Dashboard")
    print("="*50)
    print("\n  Open: http://localhost:5000")
    print("  Ctrl+C to stop\n")
    app.run(host='0.0.0.0',port=5000,debug=False)
