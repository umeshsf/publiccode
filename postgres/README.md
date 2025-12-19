
## Getting started
To import a **flow definition file** into **Openflow**, you load the JSON as a **Process Group** on a Runtime canvas.

Prereq: Postgres data and setup is ready, if not use *.sql to do so. 

### **Step‑by‑step: Import a flow definition JSON**

1. **Run the streamlit app and input all the values for postgres and Snowflake**

```shell
conda activate {yourenv}
pip install req
pip install -r requirements.txt
streamlit run app.py
```

2. **Open the Openflow canvas**  
   * In Snowsight, go to **Data → Openflow**.  
   * Click **Launch Openflow** for the Runtime where you want to run the flow.  
      [1](https://snowflakecomputing.atlassian.net/wiki/spaces/democentral/pages/4543152318)  
3. **Start creating a Process Group**  
   * In the canvas, click the **Process Group** icon (4th icon in the top toolbar: two small intersecting squares in a larger square).  
   * Drag it onto the canvas; a **Create Process Group** dialog opens.  
      [2](https://docs.google.com/document/d/1AP3VthA41ZslO8bMmLe4Urxvxe5cyIYe39tbhNYwzBc)  
4. **Select your flow definition file (the JSON)**  
   * In that dialog, click the **Browse** button to the right of the *Name* field.  
   * Choose your `*.json` flow definition file from your local machine (for example, a connector JSON like `postgres_cdc_openflow_configured.json`).  
   * Click **Add**.  
   * The imported flow appears on the canvas as a **Process Group** containing all processors and connections from the JSON.  
5. **Configure parameters**  
   * Click on Postgres cdc openflow configured  
   * Right‑click the imported process group → **Parameters**.  
   * Choose Postgress Source Parameters  
   * Fill in PostgreSQL parameter values : Postgres Password, and Postgres Driver  
   * Download postgres driver e.g 42.7.6  \- [https://jdbc.postgresql.org/download/](https://jdbc.postgresql.org/download/)   
6. **Enable controller services**  
   * Right‑click on an empty area of the canvas → **Enable all Controller Services**.  
   * Wait until services show as **Enabled** (no red warning icons).  
7. **Start the flow**  
   * Right‑click the imported process group → **Start**.  
   * The flow begins running and ingesting/moving data as defined.  
        
   * 

