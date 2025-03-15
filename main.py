import streamlit as st
import pandas as pd
import datetime
import os
from supabase import create_client, Client
from st_supabase_connection import SupabaseConnection
from PIL import Image




# データを読み込む関数
def load_data(conn,TABLE_NAME):
    # Perform query.
    response = conn.table(TABLE_NAME).select("*").execute()
    df = pd.DataFrame(data = response.data)
    df["lastasked"] = pd.to_datetime(df["lastasked"], format="ISO8601")
    return df

# データを保存する関数
def save_data(df,conn,TABLE_NAME):
    df_tmp = df.copy()
    df_tmp["lastasked"] = df_tmp["lastasked"].astype(str)
    df_tmp = df_tmp.astype({
    "id":"int64",
    "level":"int64",
    "subject":"string",
    "unit":"string",
    "exercise": "string",
    "exercise_image": "string",
    "exercise_audio": "string",
    "answer": "string",
    "answer_image":"string",
    "additional_info":"string",
    "answer_audio":"string",
    "reference":"string",
    "correct": "int64",
    "incorrect": "int64",
    "lastasked": "string",  # ISO 8601 形式に変換済みの文字列
    "delete":"int64"
    })
    for _, row in df_tmp.iterrows():
        conn.table(TABLE_NAME).upsert(row.to_dict()).execute()

# 優先出題条件に基づきデータをフィルタリング
def filter_questions(df):
    today = datetime.datetime.now()
    df["DaysSinceLastAsked"] = df["lastasked"].apply(
        lambda x: (today - pd.to_datetime(x)).days if pd.notnull(x) else float("inf")
    )
    df["Accuracy"] = df["correct"] / (df["correct"] + df["incorrect"])
    df["Accuracy"] = df["Accuracy"].fillna(0)
    df_t = df[df["delete"] != 1] #削除区分1以外が対象
    group_a = df_t[df_t["correct"] + df_t["incorrect"] == 0].sort_values(by="lastasked", na_position="first")
    group_b = df_t[(df_t["correct"] + df_t["incorrect"] == 1) & (df_t["DaysSinceLastAsked"] >= 1)]
    group_c = df_t[(df_t["correct"] + df_t["incorrect"] == 2) & (df_t["DaysSinceLastAsked"] >= 3)]
    group_d = df_t[(df_t["correct"] + df_t["incorrect"] == 3) & (df_t["DaysSinceLastAsked"] >= 7)]
    group_e = df_t[(df_t["correct"] + df_t["incorrect"] >= 4) & (df_t["Accuracy"] < 0.8)]

    selected_a = group_a.head(5)
    selected_b = group_b.head(5)
    selected_c = group_c.head(5)
    selected_d = group_d.head(5)
    selected_e = group_e.sample(n=min(5, len(group_e))) if len(group_e) > 0 else pd.DataFrame()

    selected = pd.concat([selected_a, selected_b, selected_c, selected_d, selected_e])
    remaining = df.loc[~df.index.isin(selected.index)]

    final_result = pd.concat([selected, remaining]).reset_index(drop=True)
    final_result = final_result.drop(columns=["DaysSinceLastAsked", "Accuracy"])
    return final_result

#回答結果を更新
def update_data(rec,df):
    # 更新前のデータ型を保存
    df = df.astype(str)
    update_row = pd.DataFrame(rec,index = rec.index).T.astype(str)
    df = pd.concat([df,update_row])
    return df
#出題する
def setting_questions(current_question):
    st.write(f"[科目: {current_question['subject']}]")
    st.write(f"**問題:** {current_question['exercise']}")
    st.write(f"==引用== {current_question['reference']}")
    #画像のパスがあれば画像を出力
    if current_question['exercise_image']:
        question_image = Image.open(current_question['exercise_image'])
        st.image(question_image)
        
# Streamlitアプリ
def main():
    st.title("復習問題　テスト")
    
    #初期化
    if "read_file" not in st.session_state:
        st.session_state.read_file = False
    if "data" not in st.session_state:
        st.session_state.data = None
    if "current_index" not in st.session_state:
        st.session_state.current_index = 0
    if "update_df" not in st.session_state:
        st.session_state.update_df = pd.DataFrame(columns=['id','level','subject','unit','exercise','exercise_image','exercise_audio','answer_image','additional_info','answer_audio','reference','correct','incorrect','lastasked','delete'])
    if "show_answer" not in st.session_state:
        st.session_state.show_answer = False
        
    # Initialize connection.
    conn = st.connection("supabase",type=SupabaseConnection)
    TABLE_NAME = 'review_questions'
    
    #データベースから取得して初期ロード
    #出題順を並べ替えてからセット
    if st.session_state.read_file == False:
        st.session_state.data = load_data(conn,TABLE_NAME)
        st.session_state.data = filter_questions(st.session_state.data)
        st.session_state.read_file = True
        
    #出題する問題が残っている場合は、出題を続ける。
    if (st.session_state.current_index < len(st.session_state.data)) & (st.session_state.current_index < 5):
        current_question = st.session_state.data.iloc[st.session_state.current_index]
        #出題
        setting_questions(current_question)
      
        # 答えを見るボタンを押すと答えを表示
        if st.button("答えを見る"):
            st.session_state.show_answer = True
        if st.session_state.show_answer:
            st.write(f"**答え:** {current_question['answer']}")
            if current_question["answer_image"]:
                st.write("imageあり")
                answer_image = Image.open(current_question['answer_image'])
                st.image(answer_image)
            if current_question["additional_info"]:
                st.write(current_question["additional_info"])
            # 正解ボタン
            if st.button("正解"):
                current_question["correct"] += 1
                current_question["lastasked"] = datetime.datetime.now()
                st.session_state.update_df = update_data(current_question,st.session_state.update_df)
                st.session_state.current_index += 1
                st.session_state.show_answer = False
                st.rerun()

            # 不正解ボタン
            if st.button("不正解"):
                current_question["incorrect"] += 1
                current_question["lastasked"] = datetime.datetime.now()
                st.session_state.update_df = update_data(current_question,st.session_state.update_df)
                st.session_state.current_index += 1
                st.session_state.show_answer = False
                st.rerun()
    else:
        st.write("すべての問題が終了しました！")
        save_data(st.session_state.update_df,conn,TABLE_NAME)
        st.success("記録を保存しました！お疲れ様でした。")
        st.stop()
    
    #終了ボタン
    if st.button("終了"):
       save_data(st.session_state.update_df,conn,TABLE_NAME)
       st.success("記録を保存しました！お疲れ様でした。")
       st.stop()
       
    st.write("--------メンテナンス----------------")
    #アップロード
    #uploadファイルがあるときはそのファイルでデフォルトデータを更新する。
    uploaded_file = st.file_uploader("データを更新するときはファイルをアップロードしてください", type=["csv"])
    
    if  uploaded_file is not None:
        upf = pd.read_csv(uploaded_file)
        save_data(upf,conn,TABLE_NAME)
        st.success("ファイルがアップロードされ、データが更新されました。")
        
            
    # ダウンロードボタンを追加
    st.download_button(
        label="結果をダウンロード",
        data=st.session_state.data.to_csv(index=False).encode("utf-8"),
        file_name="download_wordcards.csv",
        mime="text/csv"
    )
   
if __name__ == "__main__":
    main()
