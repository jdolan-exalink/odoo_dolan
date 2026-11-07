package platform

import "testing"

func TestParsePctListAndPreflight(t *testing.T) {
	sample := `VMID       Status     Lock         Name
101        running                 frigorifico
102        running                 administracion
105        stopped                 desarrollo
`
	list := ParsePctList(sample)
	if len(list) != 3 {
		t.Fatalf("expected 3 containers, got %d", len(list))
	}
	if list[0].VMID != 101 || list[0].Name != "frigorifico" || list[0].Status != "running" {
		t.Fatalf("unexpected container[0]: %+v", list[0])
	}
	if list[2].VMID != 105 || list[2].Status != "stopped" {
		t.Fatalf("unexpected container[2]: %+v", list[2])
	}

	storages := ParsePvesmStatus(`Name         Type     Status           Total            Used       Available        %
local-lvm    lvmthin  active       209715200        20971520       188743680   10.00%
`)
	if len(storages) != 1 || storages[0].Name != "local-lvm" {
		t.Fatalf("unexpected storages: %+v", storages)
	}

	// VMID 105 is occupied -> should fail preflight
	bad := ValidateLXCPreflight(105, 4, 8192, 80, "local-lvm", "vmbr0", list, storages)
	if bad.Ready() || bad.VMIDFree {
		t.Fatalf("expected VMID 105 conflict, got %+v", bad)
	}

	// VMID 110 is free and storage has ~180GB -> should pass preflight
	good := ValidateLXCPreflight(110, 4, 8192, 80, "local-lvm", "vmbr0", list, storages)
	if !good.Ready() {
		t.Fatalf("expected VMID 110 preflight ready, got %+v", good)
	}
}
