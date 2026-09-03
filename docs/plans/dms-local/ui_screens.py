# Generates the four UI wireframe SVGs of section 3 (화면 구상) in 01-보고용-계획서.html.
# Run from the repo root: python3 docs/plans/dms-local/ui_screens.py  (re-runnable; replaces the section in place)
import pathlib, re

# ---------- SVG helpers (theme tokens via style="" so both themes resolve) ----------
MUTED = "var(--muted)"; INK = "currentColor"; BEFORE = "var(--before)"; AFTER = "var(--after)"
ACCENT = "var(--accent)"; RED = "#B6304F"; SOFT_A = "var(--after-soft)"; SOFT_R = "var(--accent-soft)"; CODEBG = "var(--code-bg)"

def esc(s): return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
def T(x, y, s, size=11, fill=INK, anchor="start", weight=None, mono=False):
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    w = f' font-weight="{weight}"' if weight else ""
    f = ' font-family="IBM Plex Mono, monospace"' if mono else ""
    return f'<text x="{x}" y="{y}" font-size="{size}"{a}{w}{f} style="fill:{fill}">{esc(s)}</text>'
def R(x, y, w, h, stroke=INK, fill="none", rx=0, dash=None, sw=1):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    r = f' rx="{rx}"' if rx else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}"{r} stroke-width="{sw}"{d} style="stroke:{stroke};fill:{fill}"/>'
def L(x1, y1, x2, y2, stroke=INK, sw=1, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke-width="{sw}"{d} style="stroke:{stroke}"/>'
def BTN(x, y, w, h, label, primary=False, size=11):
    if primary:
        return R(x, y, w, h, stroke=RED, fill=RED, rx=3) + T(x + w/2, y + h/2 + size*0.36, label, size, "#fff", "middle", 500)
    return R(x, y, w, h, rx=3) + T(x + w/2, y + h/2 + size*0.36, label, size, INK, "middle")
def PILL(x, y, w, label, kind, h=16, size=9.5):
    col = {"red": (SOFT_R, ACCENT, ACCENT), "teal": (SOFT_A, AFTER, AFTER), "gray": ("none", BEFORE, BEFORE), "ink": (CODEBG, "none", INK)}[kind]
    return R(x, y, w, h, stroke=col[1], fill=col[0], rx=8) + T(x + w/2, y + h/2 + 3.4, label, size, col[2], "middle")
def BADGE(cx, cy, n, filled=True, r=8):
    if filled:
        return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{RED}"/>' + T(cx, cy + 3.5, str(n), 10, "#fff", "middle", mono=True)
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" style="stroke:{BEFORE}"/>' + T(cx, cy + 3.5, str(n), 10, BEFORE, "middle", mono=True)
def CLOUD(x, y, w, h, r=7, n=None):
    nw, nh = max(2, round(w / (2*r))), max(2, round(h / (2*r)))
    w, h = nw*2*r, nh*2*r; d = 1.35*r
    p = [f"M{x} {y}"]
    p += [f"q{r} {-d:.1f} {2*r} 0"] * nw
    p += [f"q{d:.1f} {r} 0 {2*r}"] * nh
    p += [f"q{-r} {d:.1f} {-2*r} 0"] * nw
    p += [f"q{-d:.1f} {-r} 0 {-2*r}"] * nh
    s = f'<path d="{" ".join(p)} z" fill="none" stroke-width="1.5" style="stroke:{ACCENT}"/>'
    if n is not None: s += BADGE(x + w, y, n)
    return s
def SVG(w, h, label, body):
    return (f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{esc(label)}">\n'
            f'<g font-family="Noto Sans KR, sans-serif" font-size="11">\n' + "\n".join(body) + "\n</g>\n</svg>")
def CHROME(w, title, right=""):
    return [R(0.5, 0.5, w-1, 30, fill=CODEBG), T(16, 20, title, 12, INK, weight=600), L(0, 30.5, w, 30.5)]

# ---------- Screen A: 세트 지정 ----------
def screen_a():
    b = CHROME(860, "리비전 도면 관리 앱 · 세트 지정")
    for x, name, col, path, cnt in [(24, "변경 전 폴더", BEFORE, "D:\\현장\\김화공고\\실시도서_REV2\\", "DWG 68 · XR 폴더 27 자동 인식"),
                                     (440, "변경 후 폴더", AFTER, "D:\\현장\\김화공고\\실시도서_REV3\\", "DWG 69 · XR 폴더 27 자동 인식")]:
        b += [R(x, 50, 396, 150, stroke=col, dash="6 4", sw=1.5, rx=4),
              T(x+16, 76, name, 13, col, weight=600),
              T(x+16, 102, path, 11, INK, mono=True),
              T(x+16, 126, cnt, 11, MUTED),
              T(x+16, 148, "표제란 읽기 완료 · 도곽 74장", 11, MUTED),
              BTN(x+300, 164, 80, 22, "폴더 선택…")]
    b += [T(24, 238, "사소한 변경 기준", 11, MUTED), R(128, 222, 64, 22, rx=3), T(160, 237, "1 mm", 11, INK, "middle", mono=True),
          T(216, 238, "클라우드 마크 규격", 11, MUTED), R(332, 222, 124, 22, rx=3), T(342, 237, "회사 표준", 11, INK), T(446, 237, "▾", 11, MUTED, "end"),
          T(480, 238, "리비전 표 양식", 11, MUTED), R(572, 222, 124, 22, rx=3), T(582, 237, "표제란 옆", 11, INK), T(686, 237, "▾", 11, MUTED, "end")]
    b += [T(24, 276, "최근 비교", 11, INK, weight=600), L(24, 284, 660, 284)]
    for i, (d, s, r_) in enumerate([("08-28", "실시도서 REV1 → REV2", "변경 9 / 도곽 74"), ("08-12", "골조샵 REV0 → REV1", "변경 4 / 도곽 5"), ("07-30", "실시도서 REV0 → REV1", "변경 21 / 도곽 72")]):
        y = 304 + i*22
        b += [T(24, y, d, 10.5, MUTED, mono=True), T(84, y, s, 11, INK), T(660, y, r_, 10.5, MUTED, "end")]
    b += [BTN(704, 304, 132, 36, "비교 시작", primary=True, size=13)]
    return SVG(860, 360, "세트 지정 화면. 변경 전 폴더와 변경 후 폴더를 지정하는 두 영역, 사소한 변경 기준과 클라우드 마크 규격과 리비전 표 양식 옵션, 최근 비교 목록, 비교 시작 버튼", b)

# ---------- Screen B: 도곽 목록 ----------
def screen_b():
    b = CHROME(860, "도곽 목록 · 실시도서 REV2 → REV3")
    x = 24
    for label, w, kind in [("전체 74", 66, "ink"), ("변경 12", 66, "red"), ("동일 58", 66, "gray"), ("신규 2", 58, "gray"), ("삭제 1", 58, "gray"), ("짝 없음 1", 78, "gray")]:
        b += [PILL(x, 44, w, label, kind, h=22, size=10.5)]; x += w + 8
    b += [R(640, 44, 196, 22, rx=3), T(650, 59, "도면번호·제목 검색", 10.5, MUTED)]
    cols = [(24, "도면번호"), (110, "도면명"), (400, "전"), (480, "후"), (560, "변경"), (700, "상태")]
    b += [T(cx, 88, c, 10, MUTED, weight=600) for cx, c in cols] + [L(24, 94, 836, 94)]
    rows = [("A-101", "1층 평면도", "REV2 08-14", "REV3 09-01", 12, "변경", "red"),
            ("A-102", "2층 평면도", "REV2 08-14", "REV3 09-01", 7, "변경", "red"),
            ("A-201", "정면도", "REV2 08-14", "REV3 09-01", 3, "변경", "red"),
            ("A-301", "단면도 A", "REV2 08-14", "REV3 09-01", 1, "변경", "red"),
            ("A-105", "지붕 평면도", "REV2 08-14", "REV3 09-01", 0, "동일", "gray"),
            ("S-104", "기초 배근도", "–", "REV3 09-01", None, "신규", "teal"),
            ("E-203", "전등 설비도", "REV2 08-14", "–", None, "삭제", "gray"),
            ("M-110", "덕트 평면도", "?", "REV3 09-01", None, "짝 없음", "gray")]
    for i, (no, name, a, c, cnt, st, kind) in enumerate(rows):
        top = 98 + i*30; y = top + 19
        if i == 1: b += [R(20, top+2, 816, 27, stroke="none", fill=SOFT_A, rx=3)]
        b += [T(24, y, no, 11, INK, mono=True), T(110, y, name, 11, INK), T(400, y, a, 10.5, MUTED, mono=True), T(480, y, c, 10.5, MUTED, mono=True)]
        if cnt: b += [R(560, top+9, cnt*8, 10, stroke="none", fill=ACCENT), T(560 + cnt*8 + 6, y, str(cnt), 11, INK, mono=True)]
        elif cnt == 0: b += [T(560, y, "–", 11, MUTED)]
        b += [PILL(700, top+6, 54, st, kind)]
        if st == "짝 없음": b += [BTN(764, top+5, 72, 18, "수동 짝 맞춤", size=10)]
        b += [L(24, top+30, 836, top+30, stroke="var(--line)")]
    b += [T(24, 372, "변경 12 도곽 · 승인 23건 · 미결 2건 · 사소한 변경 41건 접힘", 11, MUTED), BTN(448, 352, 100, 32, "도곽 열기", size=12), BTN(556, 352, 132, 32, "선택 도곽 출력…", size=12), BTN(704, 352, 132, 32, "전체 도곽 출력…", primary=True, size=12)]
    return SVG(860, 400, "도곽 목록 화면. 전체, 변경, 동일, 신규, 삭제, 짝 없음 필터와 도면번호, 도면명, 전후 리비전, 변경 수 막대, 상태 열이 있는 표. 짝 없음 행에는 수동 짝 맞춤 버튼, 아래에 도곽 열기, 선택 도곽 출력, 전체 도곽 출력 버튼", b)

# ---------- Screen C: 비교 작업 화면 ----------
def screen_c():
    b = CHROME(860, "A-102 2층 평면도 · REV2 (08-14) → REV3 (09-01)")
    # segmented view control
    b += [R(470, 8, 220, 20, rx=3), R(470, 8, 70, 20, stroke="none", fill=SOFT_A, rx=3), T(505, 22, "겹쳐 보기", 10.5, AFTER, "middle", 600),
          L(540, 8, 540, 28), T(565, 22, "전", 10.5, INK, "middle"), L(590, 8, 590, 28), T(615, 22, "후", 10.5, INK, "middle"), L(640, 8, 640, 28), T(665, 22, "나란히", 10.5, INK, "middle"),
          BTN(700, 8, 64, 20, "레이어 ▾", size=10.5), BTN(772, 8, 64, 20, "1 : 100", size=10.5)]
    # canvas
    b += [R(12, 40, 560, 420)]
    plan_before = [R(60, 80, 420, 320, stroke=BEFORE, sw=1.4), L(60, 240, 480, 240, BEFORE, 1.4), L(250, 80, 250, 240, BEFORE, 1.4),
                   R(325, 235, 10, 10, stroke=BEFORE, fill=BEFORE), L(60, 412, 480, 412, BEFORE), L(60, 406, 60, 418, BEFORE), L(480, 406, 480, 418, BEFORE),
                   T(270, 408, "8,400", 10, BEFORE, "middle", mono=True), T(120, 300, "주기: 방화문 FD-1", 10, BEFORE)]
    plan_after = [R(60, 80, 420, 320, stroke=AFTER, sw=1.4), L(60, 240, 480, 240, AFTER, 1.4), L(290, 80, 290, 240, AFTER, 1.4), L(400, 80, 400, 240, AFTER, 1.4),
                  R(355, 235, 10, 10, stroke=AFTER, fill=AFTER), L(60, 424, 480, 424, AFTER), L(60, 418, 60, 430, AFTER), L(480, 418, 480, 430, AFTER),
                  T(270, 437, "8,700", 10, AFTER, "middle", mono=True), T(120, 316, "주기: 방화문 FD-2", 10, AFTER)]
    b += plan_before + plan_after
    b += [CLOUD(236, 92, 68, 154, 7, 1), CLOUD(318, 226, 52, 30, 6, 2), CLOUD(232, 396, 90, 46, 7, 3), CLOUD(108, 286, 130, 40, 7, 4), CLOUD(386, 68, 32, 180, 7, 5)]
    # legend + navigation inside the canvas
    b += [L(24, 448, 44, 448, BEFORE, 1.6), T(50, 452, "전", 10, BEFORE), L(70, 448, 90, 448, AFTER, 1.6), T(96, 452, "후", 10, AFTER),
          f'<circle cx="122" cy="448" r="5" fill="none" stroke-width="1.5" style="stroke:{ACCENT}"/>', T(132, 452, "변경 영역 · 번호를 누르면 확대", 10, MUTED),
          R(440, 436, 124, 18, rx=3, fill=CODEBG), T(502, 449, "‹  번호 2 / 7  ›", 10.5, INK, "middle", mono=True)]
    # right panel: change list
    b += [R(584, 40, 264, 420), T(596, 60, "변경 리스트 · 7건", 12, INK, weight=600), T(596, 78, "승인 5 · 무시 1 · 미결 1", 10.5, MUTED), L(584, 86, 848, 86)]
    items = [(1, "기하", "내벽 이동 (동쪽 400mm)", "승인", "전 x=250 → 후 x=290"), (2, "기하", "기둥 C3 이동 300mm", "승인", "블록 COL-600"),
             (3, "치수", "8,400 → 8,700", "승인", "1층 X2~X4 총치수"), (4, "텍스트", "주기 FD-1 → FD-2", "승인", "레이어 A-NOTE"),
             (5, "기하", "벽 W2 신설", "승인", "레이어 A-WALL"), (6, "기하", "해치 미세 이동 0.4mm", "무시", "허용오차 이내"), (7, "텍스트", "날짜 표기 변경", "미결", "표제란 속성")]
    for i, (n, kind, desc, state, detail) in enumerate(items):
        top = 94 + i*46
        muted = state == "무시"
        b += [BADGE(602, top+14, n, filled=not muted), PILL(618, top+6, 36, kind, "ink" if not muted else "gray", h=16, size=9)]
        b += [T(662, top+18, desc, 11, MUTED if muted else INK)]
        ok = state == "승인"
        b += [R(662, top+25, 40, 15, stroke=AFTER if ok else "var(--line)", fill=SOFT_A if ok else "none", rx=3), T(682, top+36, "승인", 9.5, AFTER if ok else MUTED, "middle", 600 if ok else None),
              R(708, top+25, 40, 15, stroke=BEFORE if muted else "var(--line)", fill=CODEBG if muted else "none", rx=3), T(728, top+36, "무시", 9.5, INK if muted else MUTED, "middle"),
              T(842, top+36, detail, 9, MUTED, "end", mono=True), L(596, top+45.5, 840, top+45.5, stroke="var(--line)")]
    b += [T(596, 450, "▸ 사소한 변경 41건 접힘 (레이어·색·미세 이동)", 10.5, MUTED)]
    # footer
    b += [R(12, 470, 836, 40, fill=CODEBG), BTN(24, 479, 124, 22, "전체 도곽 출력…", primary=True), BTN(156, 479, 116, 22, "선택 도곽 출력…"), BTN(280, 479, 110, 22, "표 텍스트 복사"),
          T(836, 494, "출력은 승인 항목만 · 원본은 수정하지 않는다", 10.5, MUTED, "end")]
    return SVG(860, 520, "비교 작업 화면. 왼쪽 캔버스에 변경 전 회색과 변경 후 청록 도면이 겹쳐 있고 다섯 개의 붉은 클라우드 마크에 번호가 붙어 있다. 오른쪽 변경 리스트에는 항목마다 종류, 설명, 승인과 무시 버튼이 있고 아래에 사소한 변경이 접혀 있다. 하단에 전체 도곽 출력, 선택 도곽 출력, 표 텍스트 복사 버튼", b)

# ---------- Screen D: 출력 ----------
def screen_d():
    X, W = 110, 640
    b = [R(X, 20, W, 340, rx=4, fill="var(--surface)"), T(X+20, 46, "출력 · 실시도서 REV2 → REV3", 12, INK, weight=600), L(X, 56, X+W, 56)]
    def radio(x, y, label, sub, sel):
        out = [f'<circle cx="{x+8}" cy="{y-4}" r="5.5" fill="none" stroke-width="1.2" style="stroke:{ACCENT if sel else BEFORE}"/>']
        if sel: out.append(f'<circle cx="{x+8}" cy="{y-4}" r="3" style="fill:{ACCENT}"/>')
        out.append(T(x+22, y, label, 11, INK, weight=600 if sel else None))
        if sub: out.append(T(x+22+len(label)*10.5+8, y, sub, 10, MUTED))
        return out
    b += [T(X+20, 84, "범위", 11, INK, weight=600)]
    b += radio(X+90, 84, "전체 도곽", "변경 12 도곽 · 승인 23건 (미결 2건 제외)", True)
    b += radio(X+400, 84, "선택 도곽", "도곽 선택 대화상자에서 고른다", False)
    b += [L(X+20, 98, X+W-20, 98, stroke="var(--line)")]
    b += [T(X+20, 124, "마크업 DWG", 11, INK, weight=600),
          T(X+20, 146, "저장 위치", 10.5, MUTED), T(X+120, 146, "…\\derivatives\\REV3_markup\\  (변경된 도곽마다 1개, 12개 파일)", 10.5, INK, mono=True),
          T(X+20, 168, "레이어 · 색", 10.5, MUTED), T(X+120, 168, "REV-CLOUD · 빨강 · 원 안 번호", 10.5, INK, mono=True)]
    b += [L(X+20, 184, X+W-20, 184, stroke="var(--line)")]
    b += [T(X+20, 210, "리비전 표", 11, INK, weight=600),
          T(X+20, 232, "도곽별 표", 10.5, MUTED), T(X+120, 232, "각 도곽의 표제란 옆에 그 도곽의 항목만", 10.5, INK),
          T(X+20, 254, "전체 변경 리스트", 10.5, MUTED), T(X+120, 254, "도곽별로 묶은 표 한 장 · 표지 도곽(또는 첫 도곽)에 삽입 · 23행", 10.5, INK)]
    b += [T(X+20, 290, "넣는 방법", 11, INK, weight=600)]
    b += radio(X+90, 290, "ZWCAD에 바로 삽입", "실행 중 감지됨 · COM 연동", True)
    b += radio(X+400, 290, "DXF 조각으로 저장", "", False)
    b += [T(X+90+22, 312, "", 10)] + radio(X+90, 316, "표 텍스트 복사", "엑셀·ZWCAD 표에 붙여넣기", False)
    b += [BTN(X+W-160, 318, 64, 26, "취소"), BTN(X+W-88, 318, 72, 26, "만들기", primary=True)]
    return SVG(860, 380, "출력 대화상자. 범위는 전체 도곽이 기본이고 선택 도곽을 고르면 도곽 선택 대화상자가 뜬다. 마크업 DWG는 변경된 도곽마다 한 파일, 리비전 표는 도곽별 표와 전체 변경 리스트 두 가지, 넣는 방법은 ZWCAD에 바로 삽입, DXF 조각, 표 텍스트 복사 중 선택. 취소와 만들기 버튼", b)

def fig(svg, cap): return f'  <figure>\n    {svg}\n    <figcaption>{cap}</figcaption>\n  </figure>'

section = "\n".join([
  '  <h2><span class="num">3</span>화면 구상</h2>',
  '  <p>화면은 네 장이다. 세트 지정 → 도곽 목록 → 비교 작업 → 출력 순서로 이어지고, 시간은 대부분 세 번째 화면에서 쓴다. 출력 범위는 전체 도곽이 기본이고 선택 도곽도 된다. 그림은 배치와 동작을 잡기 위한 초안이라 세부 모양은 개발하면서 바뀐다.</p>',
  '  <h3>화면 A · 세트 지정</h3>',
  fig(screen_a(), "변경 전·후 폴더를 지정하면 XR 폴더와 도곽 수를 바로 읽어 보여준다. 결정 요청 세 가지(사소한 변경 기준, 클라우드 마크 규격, 리비전 표 양식)가 여기 옵션으로 들어간다."),
  '  <h3>화면 B · 도곽 목록</h3>',
  fig(screen_b(), "짝이 맞은 도곽을 변경 많은 순으로 보여준다. 신규·삭제·짝 없음은 따로 표시하고, 짝 없음은 이 화면에서 수동으로 맞춘다. 검토가 끝나면 여기서 전체 도곽 또는 선택 도곽을 출력한다."),
  '  <h3>화면 C · 비교 작업 화면</h3>',
  fig(screen_c(), "왼쪽은 전(회색)·후(청록) 겹쳐 보기와 클라우드 마크, 오른쪽은 변경 리스트다. 번호를 누르면 그 자리로 확대되고 항목마다 승인·무시를 정한다. 사소한 변경은 접혀 있다. 도곽을 하나씩 검토한 뒤 전체 도곽 출력으로 넘어간다."),
  '  <h3>화면 D · 출력</h3>',
  fig(screen_d(), "출력 범위는 전체 도곽이 기본이다. 변경된 도곽 전부의 마크업 DWG와 전체 변경 리스트(도곽별 묶음)를 한 번에 만들고, 일부만 필요하면 선택 도곽으로 고른다. ZWCAD가 실행 중이면 COM 연동으로 바로 삽입하고, 아니면 DXF 조각이나 표 텍스트로 넘긴다."),
  '  <p class="note"><strong>도곽 선택 대화상자.</strong> 출력 범위를 선택 도곽으로 고르면 변경된 도곽의 목록이 대화상자로 뜬다. 도면번호·도면명·승인 건수가 체크 목록으로 나오고 전체 선택·해제와 검색이 있다. 체크한 도곽만 마크업 DWG와 변경 리스트로 나간다.</p>',
  ''])

p = pathlib.Path("docs/plans/dms-local/01-보고용-계획서.html")
s = p.read_text(encoding="utf-8")
def rep(old, new, count=1):
    global s
    assert s.count(old) == count, (old[:60], s.count(old)); s = s.replace(old, new)
if '화면 구상' in s:
    a = s.index('  <h2><span class="num">3</span>화면 구상</h2>'); b = s.index('  <h2><span class="num">4</span>매뉴얼</h2>')
    s = s[:a] + section + '\n' + s[b:]
else:
    # renumber 3..7 -> 4..8 (descending to avoid collisions), then insert the new section 3 before the manual
    for n in (7, 6, 5, 4, 3):
        rep(f'<span class="num">{n}</span>', f'<span class="num">{n+1}</span>')
    rep('  <h2><span class="num">4</span>매뉴얼</h2>', section + '\n  <h2><span class="num">4</span>매뉴얼</h2>')
    # manual steps reference the screens
    refs = ["화면 A", "화면 B", "화면 B", "화면 C", "화면 C", "화면 D"]
    i = s.index('<h2><span class="num">4</span>매뉴얼</h2>'); j = s.index('</ol>', i)
    ol = s[i:j]; assert ol.count('</li>') == 6
    ol2 = ol
    for r_ in refs:
        ol2 = ol2.replace('</li>', f' <span class="tag">{r_}</span>\uFFFF', 1)
    ol2 = ol2.replace('\uFFFF', '</li>')
    s = s[:i] + ol2 + s[j:]
# card 3 wording left over from the 승인 rename
s = s.replace('채택과 무시 체크', '승인과 무시 체크').replace('항목을 고치고 채택·무시를 정한 뒤 승인하면', '항목을 고치고 승인·무시를 정한 뒤 승인하면')
assert '채택' not in s
p.write_text(s, encoding="utf-8")
print("sections:", re.findall(r'<span class="num">(\d)</span>([^<]+)', s))
print("svg count:", s.count('<svg'), "figures:", s.count('<figure'))
