# GCP setup

```bash
$ gcloud projects list
$ gcloud config set project [PROJECT_ID]
```

## Service account
Create new
```bash
gcloud iam service-accounts create SERVICE_ACCOUNT_ID \
    --description="DESCRIPTION" \
    --display-name="DISPLAY_NAME"
```

List:
```bash
$ gcloud iam service-accounts list
```

## Enable APIs for Drive and Sheets
```bash
gcloud services enable drive.googleapis.com
gcloud services enable sheets.googleapis.com
```

## Grant permission
List all roles (a lot!):
```bash
$ gcloud iam roles list
```

Create:
```bash
gcloud projects add-iam-policy-binding PROJECT_ID \
    --member="serviceAccount:SERVICE_ACCOUNT_ID@PROJECT_ID.iam.gserviceaccount.com" \
    --role="ROLE_NAME"
```
