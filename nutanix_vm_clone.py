import http.client
import json
import ssl
import time

NTNX_PRISMCENTRAL_IP = "YOUR_IP:9440"
PC_TOKEN = "YOUR GENERATED TOKEN FROM nutanix_auth.py"


def get_conn(host=NTNX_PRISMCENTRAL_IP):
    context = ssl._create_unverified_context()
    return http.client.HTTPSConnection(host, context=context)


def api_request(method, url, payload=None, host=NTNX_PRISMCENTRAL_IP, token=PC_TOKEN, extra_headers=None):
    conn = get_conn(host)
    headers = {
        "Accept": "application/json",
        "Authorization": token,
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    body = None if payload is None else payload if isinstance(payload, str) else json.dumps(payload)
    conn.request(method, url, body=body, headers=headers)
    res = conn.getresponse()
    raw = res.read().decode("utf-8")
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        data = {"raw": raw}
    if res.status >= 400:
        raise RuntimeError(f"API error {res.status} on {host}{url}: {data}")
    return data, res.status


def task_uuid(response):
    return (response.get("status", {}).get("execution_context", {}).get("task_uuid")
            or response.get("task_uuid")
            or response.get("status", {}).get("task_uuid"))


def wait_for_task(task_id, timeout=300, interval=5):
    start = time.time()
    while time.time() - start < timeout:
        data, _ = api_request("GET", f"/api/nutanix/v3/tasks/{task_id}")
        status = str(data.get("status", "")).upper()
        if status in {"SUCCEEDED", "FAILED", "ABORTED"}:
            return data
        time.sleep(interval)
    raise TimeoutError(f"Task {task_id} reached timeout after {timeout}s.")


def list_vms(page_size=100):
    offset, results = 0, []
    while True:
        payload = {"kind": "vm", "length": page_size, "offset": offset}
        data, _ = api_request("POST", "/api/nutanix/v3/vms/list", payload)
        entities = data.get("entities", [])
        if not entities:
            break
        results.extend(entities)
        total = data.get("metadata", {}).get("total_matches")
        offset += page_size
        if total is not None and offset >= total:
            break
    return results


def get_vm_by_name(name):
    for vm in list_vms():
        if vm.get("spec", {}).get("name") == name:
            return vm
    return None


def get_vm(uuid_):
    data, _ = api_request("GET", f"/api/nutanix/v3/vms/{uuid_}")
    return data


def put_vm(uuid_, vm_data, timeout=300, interval=5):
    response, _ = api_request("PUT", f"/api/nutanix/v3/vms/{uuid_}", vm_data)
    tid = task_uuid(response)
    if tid:
        result = wait_for_task(tid, timeout=timeout, interval=interval)
        if str(result.get("status", "")).upper() != "SUCCEEDED":
            raise RuntimeError(f"Task failed: {result}")
    return get_vm(uuid_)

import argparse
import copy

SUBNET_UUIDS = {"80": "SUBNET_UUID_FOR_VLAN_80", "130": "SUBNET_UUID_FOR_VLAN_130"}


def clean_clone_payload(source_vm, target_name, description=None, cpu=None, ram=None, vlan=None):
    payload = copy.deepcopy(source_vm)
    payload.pop("status", None)
    meta = payload.get("metadata", {})
    for key in ["uuid", "spec_version", "spec_hash", "creation_time", "last_update_time"]:
        meta.pop(key, None)
    meta["kind"] = "vm"
    spec = payload["spec"]
    spec["name"] = target_name
    if description is not None:
        spec["description"] = description
    res = spec["resources"]
    res["power_state"] = "OFF"
    if cpu is not None:
        res["num_sockets"] = 1
        res["num_vcpus_per_socket"] = cpu
    if ram is not None:
        res["memory_size_mib"] = ram * 1024
    for nic in res.get("nic_list", []) or []:
        nic.pop("mac_address", None)
        nic.pop("ip_endpoint_list", None)
        if vlan is not None:
            if str(vlan) not in SUBNET_UUIDS:
                raise ValueError(f"No subnet mapping for VLAN {vlan}.")
            nic["subnet_reference"] = {"kind": "subnet", "uuid": SUBNET_UUIDS[str(vlan)]}
    return payload


def set_power(uuid_, state):
    vm = get_vm(uuid_)
    vm.pop("status", None)
    vm["spec"]["resources"]["power_state"] = state.upper()
    return put_vm(uuid_, vm)


def main():
    parser = argparse.ArgumentParser(description="Clone a Nutanix VM through Prism Central.")
    parser.add_argument("--source", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--description")
    parser.add_argument("--cpu", type=int)
    parser.add_argument("--ram", type=int)
    parser.add_argument("--vlan")
    parser.add_argument("--power", choices=["on", "off"], default="off")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json-report")
    args = parser.parse_args()
    if get_vm_by_name(args.name):
        raise RuntimeError(f"Target VM '{args.name}' already exists.")
    source = get_vm_by_name(args.source)
    if not source:
        raise RuntimeError(f"Source VM '{args.source}' was not found.")
    source_vm = get_vm(source["metadata"]["uuid"])
    payload = clean_clone_payload(source_vm, args.name, args.description, args.cpu, args.ram, args.vlan)
    if args.dry_run:
        result = {"success": True, "dry_run": True, "payload": payload}
    else:
        response, _ = api_request("POST", "/api/nutanix/v3/vms", payload)
        tid = task_uuid(response)
        if tid:
            task = wait_for_task(tid, timeout=600)
            if str(task.get("status", "")).upper() != "SUCCEEDED":
                raise RuntimeError(f"Clone failed: {task}")
        target = get_vm_by_name(args.name)
        uuid_ = target["metadata"]["uuid"]
        if args.power == "on":
            set_power(uuid_, "ON")
        result = {"success": True, "source": args.source, "target": args.name, "uuid": uuid_}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.json_report:
        open(args.json_report, "w", encoding="utf-8").write(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
