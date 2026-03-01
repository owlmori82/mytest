import streamlit as st
import pandas as pd
import datetime
from PIL import Image
from st_supabase_connection import SupabaseConnection
import uuid 


# === データ操作関数 ===

def load_data(conn, TABLE_NAME):
    response = conn.table(TABLE_NAME).select("*").execute()
    df = pd.DataFrame(data=response.data)
    df["lastasked"] = pd.to_datetime(df["lastasked"], errors="coerce")
    return df

def save_data(df, conn, TABLE_NAME):
    df_tmp = df.copy()
    df_tmp["lastasked"] = df_tmp["lastasked"].astype(str)
    df_tmp["exercise_image"] = df_tmp["exercise_image"].apply(lambda x: x if pd.notna(x) and x != "None" else None)
    for _, row in df_tmp.iterrows():
        data = row.to_dict()
        data = {k: (v if pd.notna(v) and v != "None" else None) for k, v in data.items()}
        conn.table(TABLE_NAME).upsert(data).execute()

def filter_questions(df):
    today = datetime.datetime.now()
    df["DaysSinceLastAsked"] = df["lastasked"].apply(
        lambda x: (today - pd.to_datetime(x)).days if pd.notnull(x) else float("inf")
    )
    df["Accuracy"] = df["correct"] / (df["correct"] + df["incorrect"])
    df["Accuracy"] = df["Accuracy"].fillna(0)
    group_a = df[df["correct"] + df["incorrect"] == 0].sort_values(by="lastasked", na_position="first")
    group_b = df[(df["correct"] + df["incorrect"] == 1) & (df["DaysSinceLastAsked"] >= 1)]
    group_c = df[(df["correct"] + df["incorrect"] == 2) & (df["DaysSinceLastAsked"] >= 3)]
    group_d = df[(df["correct"] + df["incorrect"] == 3) & (df["DaysSinceLastAsked"] >= 7)]
    group_e = df[(df["correct"] + df["incorrect"] >= 4) & (df["Accuracy"] < 0.8)]
    selected = pd.concat([group_a.head(3), group_b.head(3), group_c.head(3), group_d.head(3),
                          group_e.sample(n=min(5, len(group_e))) if len(group_e) > 0 else pd.DataFrame()])
    remaining = df.loc[~df.index.isin(selected.index)]
    final_result = pd.concat([selected, remaining]).reset_index(drop=True)
    final_result = final_result.drop(columns=["DaysSinceLastAsked", "Accuracy"])
    return final_result[final_result["delete"] != 1]

def update_data(rec, df):
    df = df.astype(str)
    update_row = pd.DataFrame(rec, index=rec.index).T.astype(str)
    df = pd.concat([df, update_row])
    return df

def setting_questions(current_question):
    st.write(f"[科目: {current_question['subject']}]")
    st.write("**問題:**")
    st.markdown(current_question["exercise"].replace("\n","<br>"),unsafe_allow_html=True)
    st.write(f"==引用== {current_question['reference']}")
    if current_question['exercise_image']:
        question_image = Image.open(current_question['exercise_image'])
        st.image(question_image)


# === ページ1：復習問題出題 ===

def page_quiz(conn, TABLE_NAME):
    st.title("復習問題")

    if "read_file" not in st.session_state:
        st.session_state.read_file = False
    if "data" not in st.session_state:
        st.session_state.data = None
    if "current_index" not in st.session_state:
        st.session_state.current_index = 0
    if "update_df" not in st.session_state:
        st.session_state.update_df = pd.DataFrame(columns=[
            'id', 'level', 'subject', 'unit', 'exercise', 'exercise_image',
            'exercise_audio', 'answer', 'answer_image', 'additional_info',
            'answer_audio', 'reference', 'correct', 'incorrect', 'lastasked', 'delete'
        ])
    if "show_answer" not in st.session_state:
        st.session_state.show_answer = False

    if not st.session_state.read_file:
        st.session_state.data = load_data(conn, TABLE_NAME)
        st.session_state.data = filter_questions(st.session_state.data)
        st.session_state.read_file = True

    if (st.session_state.current_index < len(st.session_state.data)) and (st.session_state.current_index < 7):
        current_question = st.session_state.data.iloc[st.session_state.current_index]
        setting_questions(current_question)

        if st.button("答えを見る"):
            st.session_state.show_answer = True

        if st.session_state.show_answer:
            st.write(f"**答え:** {current_question['answer']}")
            if current_question["answer_image"]:
                answer_image = Image.open(current_question['answer_image'])
                st.image(answer_image)
            if current_question["additional_info"]:
                st.write("== 解説 ==")
                st.markdown(current_question["additional_info"].replace("\n","<br>"),unsafe_allow_html=True)
                
            if st.button("正解"):
                current_question["correct"] += 1
                current_question["lastasked"] = datetime.datetime.now()
                st.session_state.update_df = update_data(current_question, st.session_state.update_df)
                st.session_state.current_index += 1
                st.session_state.show_answer = False
                st.rerun()

            if st.button("不正解"):
                current_question["incorrect"] += 1
                current_question["lastasked"] = datetime.datetime.now()
                st.session_state.update_df = update_data(current_question, st.session_state.update_df)
                st.session_state.current_index += 1
                st.session_state.show_answer = False
                st.rerun()
    else:
        st.write("すべての問題が終了しました！")
        save_data(st.session_state.update_df, conn, TABLE_NAME)
        st.success("記録を保存しました！お疲れ様でした。")
        st.stop()

    if st.button("終了"):
        save_data(st.session_state.update_df, conn, TABLE_NAME)
        st.success("記録を保存しました！お疲れ様でした。")
        st.stop()

    st.write("--------メンテナンス----------------")
    uploaded_file = st.file_uploader("データを更新するときはファイルをアップロードしてください", type=["csv"])
    if uploaded_file is not None:
        upf = pd.read_csv(uploaded_file)
        save_data(upf, conn, TABLE_NAME)
        st.success("ファイルがアップロードされ、データが更新されました。")

    st.download_button(
        label="結果をダウンロード",
        data=st.session_state.data.to_csv(index=False).encode("utf-8"),
        file_name="download_review.csv",
        mime="text/csv"
    )


# === ページ2：新規問題の登録 ===

def page_register(conn, TABLE_NAME):
    st.title("新しい問題の登録")

    def get_next_id():
        existing_data = load_data(conn, TABLE_NAME)
        if existing_data.empty:
            return 1
        else:
            existing_ids = pd.to_numeric(existing_data["id"], errors="coerce")
            return int(existing_ids.max()) + 1

    # IDをセッション状態で保持・更新
    if "next_id" not in st.session_state:
        st.session_state.next_id = get_next_id()

    next_id = st.session_state.next_id
    st.info(f"この問題のIDは `{next_id}` に自動設定されます。")
    
    # 一意なキーを生成
    if "form_key" not in st.session_state:
        st.session_state.form_key = str(uuid.uuid4())
    form_key = st.session_state.form_key

    # 入力フォーム
    subject = st.selectbox("科目（必須）",("算数","英語","理科","社会","国語"))
    unit = st.text_input("単元（必須）", key=f"unit_{form_key}")
    level = st.selectbox("レベル", [1, 2, 3, 4, 5], key=f"level_{form_key}")
    exercise = st.text_area("問題文（必須）", key=f"exercise_{form_key}")
    show_exercise = st.checkbox("問題文を確認", value=True, key=f"show_exercise_{form_key}")
    if show_exercise and exercise:
        st.markdown("#### 🔍 問題文プレビュー")
        st.markdown(exercise.replace("\n", "<br>"), unsafe_allow_html=True)

    auto_exercise_image = st.checkbox("問題画像を自動設定する", value=False, key=f"auto_exercise_image_{form_key}")
    exercise_image_path = f"./data/{next_id}_問題.jpg" if auto_exercise_image else st.text_input("問題画像のパス", key=f"exercise_image_{form_key}")

    answer = st.text_area("答え（必須）", key=f"answer_{form_key}")
    st.markdown("#### 📝 答えプレビュー")
    st.markdown(answer.replace("\n", "<br>"), unsafe_allow_html=True)

    auto_answer_image = st.checkbox("答え画像を自動設定する", value=False, key=f"auto_answer_image_{form_key}")
    answer_image_path = f"./data/{next_id}_解答.jpg" if auto_answer_image else st.text_input("答え画像のパス", key=f"answer_image_{form_key}")

    additional_info = st.text_area("解説", key=f"additional_info_{form_key}")
    show_info = st.checkbox("解説を確認", value=True, key=f"show_info_{form_key}")
    if show_info and additional_info:
        st.markdown("#### 📝 解説プレビュー")
        st.markdown(additional_info.replace("\n", "<br>"), unsafe_allow_html=True)

    reference = st.text_input("出典（必須）", key=f"reference_{form_key}")
    
    delete = st.selectbox("削除フラグ", [0,1], key=f"delete_{form_key}")


    if st.button("この内容で問題を登録"):
        if subject and unit and exercise and answer:
            new_question = {
                "id": str(next_id),
                "level": level,
                "subject": subject,
                "unit": unit,
                "exercise": exercise,
                "exercise_image": exercise_image_path if exercise_image_path else None,
                "exercise_audio": None,
                "answer": answer,
                "answer_image": answer_image_path if answer_image_path else None,
                "answer_audio": None,
                "additional_info": additional_info,
                "reference": reference,
                "correct": 0,
                "incorrect": 0,
                "lastasked": datetime.datetime.now().isoformat(),
                "delete": delete
            }
            conn.table(TABLE_NAME).insert(new_question).execute()
            st.success("新しい問題が登録されました！")
            #セッション状態をクリアして再実行
            st.session_state.clear()
            st.rerun()
        else:
            st.error("科目・単元・問題文・答え・出典は必須です。")

# === ページ3：既存問題の修正 ===

def page_edit(conn, TABLE_NAME):
    st.title("問題の修正")

    df = load_data(conn, TABLE_NAME)

    # ID指定
    edit_id = st.text_input("修正したい問題のIDを入力してください")
    if not edit_id:
        st.info("IDを入力すると、その問題を編集できます。")
        return

    target = df[df["id"].astype(str) == str(edit_id)]
    if target.empty:
        st.error("指定したIDのデータが見つかりません。")
        return

    row = target.iloc[0]

    # === 入力フォーム ===
    subject = st.selectbox(
        "科目", ("算数", "英語", "理科", "社会", "国語"),
        index=("算数","英語","理科","社会","国語").index(row["subject"]) 
        if row["subject"] in ["算数","英語","理科","社会","国語"] else 0
    )
    unit = st.text_input("単元", value=row["unit"])
    level = st.selectbox("レベル", [1,2,3,4,5],
                         index=[1,2,3,4,5].index(int(row["level"])) if str(row["level"]).isdigit() else 0)

    # 問題文
    exercise = st.text_area("問題文", value=row["exercise"], key="edit_exercise")
    if exercise:
        st.markdown("#### 🔍 問題文プレビュー")
        st.markdown(exercise.replace("\n", "<br>"), unsafe_allow_html=True)

    auto_exercise_image = st.checkbox("問題画像を自動設定する", value=False, key=f"auto_exercise_image_{edit_id}")
    exercise_image = f"./data/{edit_id}_問題.jpg" if auto_exercise_image else st.text_input("問題画像のパス", value=row.get("exercise_image", ""), key="edit_exercise_image")

    # 答え
    answer = st.text_area("答え", value=row["answer"], key="edit_answer")
    if answer:
        st.markdown("#### 📝 答えプレビュー")
        st.markdown(answer.replace("\n", "<br>"), unsafe_allow_html=True)

    auto_answer_image = st.checkbox("答え画像を自動設定する", value=False, key=f"auto_answer_image_{edit_id}")
    answer_image = f"./data/{edit_id}_解答.jpg" if auto_answer_image else st.text_input("答え画像のパス", value=row.get("answer_image", ""), key="edit_answer_image")

    # 解説
    additional_info = st.text_area("解説", value=row.get("additional_info", ""), key="edit_additional")
    if additional_info:
        st.markdown("#### 📝 解説プレビュー")
        st.markdown(additional_info.replace("\n", "<br>"), unsafe_allow_html=True)

    reference = st.text_input("出典", value=row["reference"])
    delete_flag = st.checkbox("削除フラグ", value=bool(row["delete"]))

    # === 保存ボタン ===
    if st.button("この内容で保存"):
        updated_question = {
            "id": str(edit_id),
            "level": level,
            "subject": subject,
            "unit": unit,
            "exercise": exercise,
            "exercise_image": exercise_image if exercise_image else None,
            "exercise_audio": row.get("exercise_audio"),
            "answer": answer,
            "answer_image": answer_image if answer_image else None,
            "answer_audio": row.get("answer_audio"),
            "additional_info": additional_info,
            "reference": reference,
            "correct": int(row["correct"]),
            "incorrect": int(row["incorrect"]),
            "lastasked": row["lastasked"].isoformat() if isinstance(row["lastasked"], datetime.datetime) else str(row["lastasked"]),
            "delete": 1 if delete_flag else 0
        }
        conn.table(TABLE_NAME).upsert(updated_question).execute()
        st.success(f"ID {edit_id} の問題を更新しました！")

# === メインアプリ ===

def main():
    conn = st.connection("supabase", type=SupabaseConnection)
    # TABLE_NAME = 'develop_review_questions'
    TABLE_NAME = 'review_questions'

    page = st.sidebar.selectbox("ページを選択", ["問題出題", "問題登録", "問題修正"])

    if page == "問題出題":
        page_quiz(conn, TABLE_NAME)
    elif page == "問題登録":
        page_register(conn, TABLE_NAME)
    elif page == "問題修正":
        page_edit(conn, TABLE_NAME)

if __name__ == "__main__":
    main()
