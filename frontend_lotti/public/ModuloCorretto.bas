Attribute VB_Name = "ModuloCorretto"
Option Explicit

Sub Stampa_Pagina()
    Dim copie As Variant
    On Error GoTo Errore
    
    ActiveWorkbook.Save
    copie = InputBox("Quante copie?", "Stampa", 1)
    If copie = "" Or Not IsNumeric(copie) Then Exit Sub
    If CInt(copie) < 1 Then Exit Sub
    
    ActiveWindow.SelectedSheets.PrintOut Copies:=CInt(copie)
    Exit Sub
Errore:
    MsgBox "Errore: " & Err.Description, vbExclamation
End Sub

Sub Pagina_Iniziale()
    On Error Resume Next
    Sheets("Lotto").Select
End Sub

Sub Cancella_Lotto()
    On Error Resume Next
    ActiveSheet.Range("D11:D30").ClearContents
End Sub

Sub Carica_Lotto()
    Dim codice As String
    Dim ws As Worksheet
    Dim cella As Range
    Dim i As Long
    
    On Error GoTo Errore
    Set ws = ActiveSheet
    
    If ws.Range("B8").Value = "" Then
        MsgBox "Inserisci il prodotto in B8", vbExclamation
        Exit Sub
    End If
    
    Application.ScreenUpdating = False
    codice = ws.Range("B8").Value
    
    Set cella = Worksheets("ricette").Range("A:A").Find(codice, LookIn:=xlValues, LookAt:=xlWhole)
    
    If cella Is Nothing Then
        MsgBox "Prodotto non trovato!", vbExclamation
        Application.ScreenUpdating = True
        Exit Sub
    End If
    
    For i = 0 To 19
        ws.Range("B" & (11 + i)).Value = cella.Offset(0, i).Value
    Next i
    
    Application.ScreenUpdating = True
    MsgBox "Caricato!", vbInformation
    Exit Sub
Errore:
    Application.ScreenUpdating = True
    MsgBox "Errore: " & Err.Description, vbExclamation
End Sub

Sub Salva_PDF()
    Dim percorso As String
    Dim nome As String
    
    On Error GoTo Errore
    percorso = ThisWorkbook.Path
    If percorso = "" Then percorso = Environ("USERPROFILE") & "\Documents"
    
    nome = "Lotto_" & Format(Date, "YYYYMMDD_HHMMSS") & ".pdf"
    ActiveWorkbook.Save
    ActiveSheet.ExportAsFixedFormat xlTypePDF, percorso & "\" & nome, , , , , , True
    MsgBox "PDF salvato in: " & percorso, vbInformation
    Exit Sub
Errore:
    MsgBox "Errore PDF: " & Err.Description, vbExclamation
End Sub

Sub Stampa_Lotto()
    On Error GoTo Errore
    Sheets("Stampa_Lotto").Range("D2:D21").Value = Sheets("Lotto").Range("D11:D30").Value
    MsgBox "Copiato!", vbInformation
    Exit Sub
Errore:
    MsgBox "Errore: " & Err.Description, vbExclamation
End Sub

Sub Lotto()
    Dim wsL As Worksheet
    Dim wsA As Worksheet
    Dim riga As Long
    Dim num As Long
    Dim i As Long
    Dim dataP As Variant
    Dim dataS As Variant
    Dim dataL As Variant
    
    On Error GoTo Errore
    Application.ScreenUpdating = False
    
    Set wsL = Sheets("Lotto")
    Set wsA = Sheets("Archivio_Lotto")
    
    riga = wsA.Cells(wsA.Rows.Count, "B").End(xlUp).Row
    If riga < 2 Then riga = 2
    
    If IsNumeric(wsA.Cells(riga, 1).Value) Then
        num = wsA.Cells(riga, 1).Value + 1
    Else
        num = 1
    End If
    
    riga = riga + 1
    
    wsA.Cells(riga, 1).Value = num
    wsA.Cells(riga, 2).Value = wsL.Range("D11").Value
    
    For i = 0 To 14
        wsA.Cells(riga, 3 + i).Value = wsL.Range("D" & (12 + i)).Value
    Next i
    
    dataP = wsL.Range("D27").Value
    dataS = wsL.Range("D28").Value
    dataL = wsL.Range("D29").Value
    
    If IsDate(dataP) Then
        wsA.Cells(riga, 18).Value = CDate(dataP)
        wsA.Cells(riga, 18).NumberFormat = "DD/MM/YYYY"
    ElseIf IsNumeric(dataP) And dataP > 19000000 Then
        wsA.Cells(riga, 18).Value = DateSerial(Left(dataP, 4), Mid(dataP, 5, 2), Right(dataP, 2))
        wsA.Cells(riga, 18).NumberFormat = "DD/MM/YYYY"
    Else
        wsA.Cells(riga, 18).Value = dataP
    End If
    
    If IsDate(dataS) Then
        wsA.Cells(riga, 19).Value = CDate(dataS)
        wsA.Cells(riga, 19).NumberFormat = "DD/MM/YYYY"
    ElseIf IsNumeric(dataS) And dataS > 19000000 Then
        wsA.Cells(riga, 19).Value = DateSerial(Left(dataS, 4), Mid(dataS, 5, 2), Right(dataS, 2))
        wsA.Cells(riga, 19).NumberFormat = "DD/MM/YYYY"
    Else
        wsA.Cells(riga, 19).Value = dataS
    End If
    
    If IsDate(dataL) Then
        wsA.Cells(riga, 20).Value = Format(CDate(dataL), "YYYYMMDD")
    ElseIf IsNumeric(dataL) Then
        wsA.Cells(riga, 20).Value = CStr(dataL)
    Else
        wsA.Cells(riga, 20).Value = dataL
    End If
    wsA.Cells(riga, 20).NumberFormat = "@"
    
    wsA.Cells(riga, 21).Value = wsL.Range("D30").Value
    
    wsA.Columns("A:U").AutoFit
    Application.ScreenUpdating = True
    wsL.Select
    
    MsgBox "Lotto " & num & " archiviato!" & vbCr & "Prodotto: " & wsL.Range("D11").Value, vbInformation
    Exit Sub
Errore:
    Application.ScreenUpdating = True
    MsgBox "Errore: " & Err.Description, vbExclamation
End Sub

Sub Copia_Lotto()
    On Error GoTo Errore
    Sheets("Lotto").Range("D11:D30").Value = Sheets("Lotto").Range("B11:B30").Value
    Sheets("Stampa_Lotto").Range("D2:D21").Value = Sheets("Lotto").Range("B11:B30").Value
    MsgBox "Copiato!", vbInformation
    Exit Sub
Errore:
    MsgBox "Errore: " & Err.Description, vbExclamation
End Sub

Sub Stampa_Archivio()
    Dim percorso As String
    Dim nome As String
    
    On Error GoTo Errore
    percorso = ThisWorkbook.Path
    If percorso = "" Then percorso = Environ("USERPROFILE") & "\Documents"
    
    nome = "Archivio_" & Format(Date, "YYYYMMDD") & ".pdf"
    Sheets("Archivio_Lotto").ExportAsFixedFormat xlTypePDF, percorso & "\" & nome, , , , , , True
    MsgBox "Archivio PDF salvato!", vbInformation
    Exit Sub
Errore:
    MsgBox "Errore: " & Err.Description, vbExclamation
End Sub
