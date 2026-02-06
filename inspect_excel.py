
import openpyxl
import json

def inspect_excel(file_path):
    try:
        wb = openpyxl.load_workbook(file_path, data_only=True)
        ws = wb.active
        print(f"Sheet: {ws.title}")
        
        # Look at first 20 rows
        for r in range(1, 21):
            row_data = [ws.cell(row=r, column=c).value for c in range(1, 15)]
            print(f"Row {r}: {row_data}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect_excel("8.iiD-Plan Evaluation 1 (1).xlsx")
