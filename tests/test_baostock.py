from pathlib import Path

import baostock as bs
import pandas as pd


def main():
    print("正在连接 Baostock...")

    lg = bs.login()
    print("登录状态:", lg.error_code, lg.error_msg)

    if lg.error_code != "0":
        print("登录失败，请检查网络或服务状态")
        return

    try:
        print("\n正在获取贵州茅台历史日线...")

        rs = bs.query_history_k_data_plus(
            "sh.600519",
            "date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,isST",
            start_date="2026-01-01",
            end_date="2026-10-30",
            frequency="d",
            adjustflag="2"
        )

        if rs.error_code != "0":
            print("行情查询失败:", rs.error_msg)
            return

        rows = []

        while rs.next():
            rows.append(rs.get_row_data())

        df = pd.DataFrame(rows, columns=rs.fields)

        if df.empty:
            print("没有获取到行情数据")
            return

        print("\n获取成功！")
        print("数据总数:", len(df))
        print("\n最近10条数据：")
        print(df.tail(10).to_string(index=False))
        # 创建 CSV 目录（不存在则自动创建）
        csv_dir = Path("tests") / "csv"
        csv_dir.mkdir(parents=True, exist_ok=True)
        df.to_csv(
            "tests/csv/aotai_history.csv",
            index=False,
            encoding="utf-8-sig"
        )

        print("\n数据已保存到 maotai_history.csv")

    finally:
        bs.logout()
        print("\nBaostock 已退出")


if __name__ == "__main__":
    main()
