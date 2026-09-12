"""Transparent Korean rules, not a trained fraud classifier."""
import re

RULES = {
    "기관 신원 주장": r"(?:검찰|검사|경찰|금융감독원|금감원|은행).{0,12}(?:입니다|인데|담당|수사|직원)",
    "긴급 압박": r"지금\s*당장|즉시|빨리|오늘\s*안에|체포|구속",
    "확인 차단": r"아무(?:에게|한테)도.{0,12}(?:말|알리)|비밀로|전화.{0,6}끊지\s*마|가족.{0,12}알리지",
    "자금 이전 요청": r"(?:송금|입금|이체).{0,8}(?:해|하|해줘|하세요|부탁)|돈.{0,8}(?:보내|옮겨)|안전\s*계좌",
    "앱 설치 요청": r"(?:앱|어플|프로그램|원격).{0,12}설치",
    "인증 정보 요청": r"(?:인증번호|비밀번호|보안카드|OTP|오티피).{0,12}(?:알려|불러|보내|말씀|입력)",
}
CONTEXT = re.compile(r"(?:라는|하는|라고).{0,12}(?:사기|사례|수법|보도|교육)|(?:사기|피싱).{0,12}(?:예시|사례)")
NEGATION = re.compile(r"하지\s*(?:마|않)|말아|안\s*됩니다|요구하지|요청하지|속지")


def analyze_patterns(text):
    if not text or not text.strip():
        return {"status": "판단 보류", "level": "정보 부족", "evidence": [], "message": "분석할 대화 내용이 없습니다."}
    evidence = []
    for sentence in re.split(r"[.!?。\n]+", text[:20000]):
        for label, pattern in RULES.items():
            for match in re.finditer(pattern, sentence, re.IGNORECASE):
                local = sentence[max(0, match.start() - 24):match.end() + 32]
                contextual = bool(CONTEXT.search(local) or NEGATION.search(local))
                evidence.append({"pattern": label, "snippet": local.strip(),
                                 "context": "교육·인용·부정 가능성" if contextual else "요구·주장 신호",
                                 "active": not contextual})
    active = {e["pattern"] for e in evidence if e["active"]}
    actions = active & {"자금 이전 요청", "앱 설치 요청", "인증 정보 요청"}
    pressure = active & {"기관 신원 주장", "긴급 압박", "확인 차단"}
    level = "확인 권고" if actions and pressure else "단일 신호" if active else "근거 부족"
    return {"status": "분석 완료", "level": level, "evidence": evidence,
            "message": "학습 모델이 아닌 한국어 규칙 기반 실험입니다. 단어 조합은 사기의 증명이 아니며, 미검출도 안전을 뜻하지 않습니다."}
