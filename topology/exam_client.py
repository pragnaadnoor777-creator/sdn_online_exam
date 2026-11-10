import urllib.request, time
for i in range(60):
    try:

        with urllib.request.urlopen("http://10.0.0.100:8080/exam",timeout=5) as r:


            r.read()
    except Exception as e:

        print("fetch error:", e)
    time.sleep(0.15)

 