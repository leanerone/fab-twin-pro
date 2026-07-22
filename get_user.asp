<%
Response.ContentType = "application/json"
Dim user
user = Request.ServerVariables("LOGON_USER")
If user = "" Then
    Response.Write "{""success"":false,""message"":""No user authenticated""}"
Else
    Response.Write "{""success"":true,""username"":""" & Replace(user, """", """""""") & """}"
End If
%>