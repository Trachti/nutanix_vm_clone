# Nutanix VM Clone Script

Clone a Nutanix VM through Prism Central and optionally adjust CPU, RAM, VLAN, description, and power state.

## Features

- Finds source VM by name
- Creates target VM from source spec
- Removes source UUID, MAC addresses, and IP endpoints
- Optionally changes CPU, RAM, VLAN, and description
- Supports dry-run mode

## Configuration

Edit `nutanix_vm_clone.py`:

```python
NTNX_PRISMCENTRAL_IP = "YOUR_IP:9440"
PC_TOKEN = "YOUR GENERATED TOKEN FROM nutanix_auth.py"
SUBNET_UUIDS = {...}
```

## Usage

```bash
python nutanix_vm_clone.py --source template01 --name server-new-01 --dry-run
python nutanix_vm_clone.py --source template01 --name server-new-01 --cpu 4 --ram 8 --vlan 80 --power on
```

## Safety Notes

Always review the dry-run payload first. Do not commit real tokens, UUIDs, IP addresses, or internal details.

## Disclaimer

Example script. Test in a safe environment before production use.
