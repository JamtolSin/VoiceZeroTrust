const $ = id => document.getElementById(id);
let generated = null, audioUrl = null, running = false;
$('endpoint').value = window.VZT_CONFIG?.endpoint || '';
document.querySelectorAll('[data-page]').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('.page').forEach(page => page.hidden = page.id !== button.dataset.page);
  document.querySelectorAll('nav [data-page]').forEach(item => item.classList.toggle('active', item.dataset.page === button.dataset.page));
  $('breadcrumb').textContent = {home:'홈',lab:'실험실',benchmark:'모델 성능 비교'}[button.dataset.page];
  window.scrollTo(0, 0);
}));
const rows = [ ['ElevenLabs',300,20.67,72,99], ['MMSTTS',200,99.5,100,13], ['MeloTTS',100,68,100,94], ['SeamlessM4T-TTS',153,88.89,88.89,98.04], ['VITS-AIHUB',1507,49.70,13.21,99.20] ];
for (const [name,count,...rates] of rows) {
  const row = document.createElement('tr');
  [name,count.toLocaleString(),...rates.map(n => n.toFixed(2)+'%')].forEach((text,index) => {
    const cell = document.createElement('td'); cell.textContent = text;
    if(index === 4 && name === 'MMSTTS') cell.className = 'bad';
    row.append(cell);
  }); $('benchmark-rows').append(row);
}
function connection() {
  const raw = $('endpoint').value.trim().replace(/\/$/,'');
  const url = new URL(raw);
  if(url.protocol !== 'https:' && !(url.protocol === 'http:' && url.hostname === '127.0.0.1')) throw Error('HTTPS 모델 서버 주소를 입력해 주세요.');
  const token = $('token').value.trim();
  if(!token) throw Error('촬영용 연결 키를 입력해 주세요.');
  return {url:raw, token};
}
async function api(path, options={}) {
  const {url,token} = connection();
  let response;
  try { response = await fetch(url + path, {...options, headers:{Authorization:'Bearer '+token}, signal:AbortSignal.timeout(30000)}); }
  catch { throw Error('모델 서버에 연결하지 못했습니다. 서버 주소·연결 상태를 확인해 주세요.'); }
  const data = await response.json().catch(() => ({}));
  if(!response.ok) throw Error(data.detail || '요청에 실패했습니다 ('+response.status+').');
  return data;
}
$('connect').onclick = async () => {
  $('connection-state').textContent = '확인 중…';
  try { const result = await api('/health'); $('connection-state').textContent = result.busy ? '연결됨 · 모델 처리 중' : '연결됨 · 요청 가능'; }
  catch(error) { $('connection-state').textContent = error.message; }
};
async function run(operation,file,statusId) {
  if(running) throw Error('현재 작업이 끝난 뒤 다시 시도해 주세요.');
  if(!file) throw Error('음성 파일을 선택해 주세요.');
  if(file.size > 20*1024*1024) throw Error('20MB 이하 파일을 사용해 주세요.');
  if(operation === 'generate' && (!$('consent').checked || !$('license').checked)) throw Error('음성 사용 동의와 모델 이용 조건을 확인해 주세요.');
  if(operation === 'detect' && !$('detection-consent').checked) throw Error('음성 분석 사용 동의를 확인해 주세요.');
  if(operation === 'generate' && !$('reference').value.trim()) throw Error('녹음에서 실제로 말한 내용을 입력해 주세요.');
  if(operation === 'detect' && $('profile').value === 'korean-research' && !$('research').checked) throw Error('v4 비상업 연구·평가 이용 범위를 확인해 주세요.');
  running = true;
  ['generate','detect','detect-generated'].forEach(id => $(id).disabled = true);
  try {
    const form = new FormData(); form.append('audio',file,file.name || 'generated.wav');
    form.append('consent','true'); form.append('license',String($('license').checked));
    form.append('transcript',operation === 'generate' ? $('reference').value : '');
    form.append('profile',$('profile').value); form.append('research',String($('research').checked));
    $(statusId).textContent = '음성 전송 중…';
    const job = await api('/jobs/'+operation,{method:'POST',body:form});
    const start = Date.now();
    while(Date.now()-start < 20*60*1000) {
      $(statusId).textContent = `실제 모델 처리 중 · ${Math.floor((Date.now()-start)/1000)}초 경과\n첫 실행은 모델 다운로드와 로딩이 필요합니다.`;
      await new Promise(resolve => setTimeout(resolve,2000));
      const state = await api('/jobs/'+encodeURIComponent(job.id));
      if(state.status === 'failed') throw Error(state.error);
      if(state.status === 'complete') return state.result;
    }
    throw Error('대기 시간이 초과되었습니다. 서버에서 처리 상태를 확인해 주세요.');
  } finally {
    running = false; $('generate').disabled = false; $('detect').disabled = false; $('detect-generated').disabled = !generated;
  }
}
$('generate').onclick = async () => {
  try {
    const result = await run('generate',$('source').files[0],'generation-status');
    const bytes = Uint8Array.from(atob(result.audio_base64),c=>c.charCodeAt(0));
    generated = new File([bytes],'generated.wav',{type:'audio/wav'});
    if(audioUrl) URL.revokeObjectURL(audioUrl); audioUrl = URL.createObjectURL(generated);
    $('generated-audio').src = audioUrl; $('generated-audio').hidden = false;
    $('generation-status').textContent = `합성 완료 · ${result.model}\n입력 ${result.input_seconds.toFixed(1)}초 · 실제 처리 ${result.elapsed_seconds.toFixed(1)}초`;
    $('detect-generated').disabled = false;
  } catch(error) { $('generation-status').textContent = error.message; }
};
async function detect(file) {
  try {
    const result = await run('detect',file,'detection-status');
    const acoustic = result.acoustic, box = $('result');
    box.querySelector('strong').textContent = acoustic.decision || acoustic.status;
    box.querySelector('p').textContent = (acoustic.fake_score == null ? '' : `합성 클래스 점수 ${(acoustic.fake_score*100).toFixed(2)}% · 임계값 ${acoustic.threshold}\n`) + (acoustic.message || '');
    $('detection-status').textContent = `${acoustic.status} · ${result.audio.duration_seconds.toFixed(1)}초 · ${acoustic.profile || ''}\n${result.recommendation}`;
  } catch(error) { $('detection-status').textContent = error.message; }
}
$('detect').onclick = () => detect($('detection-source').files[0]);
$('detect-generated').onclick = () => detect(generated);
