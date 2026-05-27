@echo off
echo === Création du venv pour Script_calcul2 (Portance des pistes) ===
python -m venv venv
call venv\Scripts\activate
pip install --upgrade pip
pip install PyQt5 pandas numpy matplotlib scipy openpyxl xlrd
echo.
echo === Installation terminée. Pour lancer l'application : ===
echo   call venv\Scripts\activate
echo   python main.py
pause
