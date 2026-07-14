import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
import os

# ==========================================
# 원본 데이터 로드
# ==========================================
df = pd.read_csv("ai4i2020.csv")

# ==========================================
# 7:3 분리 (학습용 / 시뮬레이션용)
# ==========================================
df_kb, df_sim = train_test_split(df, test_size=0.3, random_state=42)

print(f"전체 데이터: {len(df)}개")
print(f"학습용(KB): {len(df_kb)}개")
print(f"시뮬레이션용: {len(df_sim)}개")

# 출력 폴더 생성
os.makedirs("processed", exist_ok=True)

# ==========================================
# [파이프라인 1] 시뮬레이션용 전처리 (라벨 제거, 원본 유지)
# ==========================================
def preprocess_for_simulation(data):
    # 라벨 컬럼 제거, 센서 데이터만 유지
    sim_columns = ['UDI', 'Product ID', 'Type', 'Air temperature [K]', 'Process temperature [K]', 
                   'Rotational speed [rpm]', 'Torque [Nm]', 'Tool wear [min]']
    return data[sim_columns].reset_index(drop=True)


# ==========================================
# [파이프라인 2] RAG 지식망용 전처리 (7,000개 학습 데이터에서 고장 이력 추출)
# ==========================================
def preprocess_for_rag(data):
    df_failures = data[data['Machine failure'] == 1].copy()
    
    failure_map = {
        'TWF': ('공구 마모(TWF)', '공구(Tool) 부품 교체가 필요합니다.'),
        'HDF': ('열 방산 실패(HDF)', '냉각 장치 및 방열 부품 점검/교체가 필요합니다.'),
        'PWF': ('전력 고장(PWF)', '전원 공급 장치 및 전력 회로 부품 교체가 필요합니다.'),
        'OSF': ('과부하 고장(OSF)', '모터 과부하 방지 부품 및 구동축 점검이 필요합니다.'),
        'RNF': ('랜덤 고장(RNF)', '특정 부품의 문제가 아니므로 전반적인 장비 점검 및 설치 환경 요인을 조사해야 합니다.')
    }
    
    rag_documents = []
    for _, row in df_failures.iterrows():
        udi = row['UDI']
        
        causes_info = [failure_map[col] for col in failure_map if row[col] == 1]
        cause_names = [item[0] for item in causes_info]
        solutions = [item[1] for item in causes_info]
        
        if not causes_info:
            cause_text = "알 수 없는 원인(기타)"
            solution_text = "데이터상으로 특정된 고장 원인이 없습니다. 현장 작업자가 직접 장비를 육안으로 점검하고 이상 여부를 판단해야 합니다."
        elif "랜덤 고장(RNF)" in cause_names:
            cause_text = ", ".join(cause_names)
            solution_text = "전반적인 장비 점검 및 설치 환경 요인을 조사해야 합니다."
        else:
            cause_text = ", ".join(cause_names)
            solution_text = " ".join(dict.fromkeys(solutions))

        doc = (
            f"제품 번호(UDI) {udi} (장비 등급 {row['Type']})에서 고장이 발생했습니다. "
            f"센서 상태: 공기 온도 {row['Air temperature [K]']}K, 공정 온도 {row['Process temperature [K]']}K, "
            f"토크 {row['Torque [Nm]']}Nm, 회전 속도 {row['Rotational speed [rpm]']}rpm, "
            f"공구 마모 {row['Tool wear [min]']}분. "
            f"확인된 원인: {cause_text}. "
            f"조치 사항: {solution_text}"
        )
        rag_documents.append(doc)
        
    return rag_documents


# ==========================================
# 실행 및 파일 저장
# ==========================================

# 1. 시뮬레이션용 CSV (3,000개 → 라벨 없이 원본 유지)
df_sim_processed = preprocess_for_simulation(df_sim)
df_sim_processed.to_csv("processed/simulator_data.csv", index=False, encoding="utf-8-sig")

# 2. KB용 CSV (7,000개 → 고장 라벨 포함 원본 보존)
df_kb.to_csv("processed/kb_data.csv", index=False, encoding="utf-8-sig")

# 3. RAG 지식망용 TXT (7,000개 중 고장 건만 자연어 문서화)
rag_docs = preprocess_for_rag(df_kb)
with open("processed/rag_history_knowledge.txt", "w", encoding="utf-8-sig") as f:
    for doc in rag_docs:
        f.write(doc + "\n")

# ==========================================
# 결과 출력
# ==========================================
print(f"\n=== 전처리 완료 ===")
print(f"[KB 학습용]       processed/kb_data.csv              ({len(df_kb)}행, 라벨 포함)")
print(f"[시뮬레이션용]    processed/simulator_data.csv       ({len(df_sim_processed)}행, 라벨 없음)")
print(f"[RAG 고장이력]    processed/rag_history_knowledge.txt ({len(rag_docs)}개 문서)")
