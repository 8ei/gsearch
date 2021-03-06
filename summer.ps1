Add-Type -AssemblyName System.Web
$input_text = [System.Web.HttpUtility]::UrlDecode($args[0])
$input_text = [System.Web.HttpUtility]::UrlDecode($input_text)
$input_text = $input_text.replace("zzzzzxxxxxzzzzzxxxxx", "(")
$input_text = $input_text.replace("xxxxxzzzzzxxxxxzzzzz", ")")
$input_text = $input_text.replace("xxxxxzzzzzxxxxxccccc", "+")
$input_text = $input_text.TrimStart("summer:")
$input_text = $input_text.Split("|")

write-host $input_text

if($input_text[0] -eq "fe"){
    & explorer.exe "/select," $input_text[1]
}elseif($input_text[0] -eq "p") {
    & "C:\Program Files\DAUM\PotPlayer\PotPlayerMini64.exe" $input_text[1]
}elseif($input_text[0] -eq "pa") {
    & "C:\Program Files\DAUM\PotPlayer\PotPlayerMini64.exe" $input_text[1] /add
}