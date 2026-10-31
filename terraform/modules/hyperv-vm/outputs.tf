output "name" {
  value = hyperv_machine_instance.this.name
}

output "ipv4_address" {
  description = "First IPv4 address reported by the guest (link-local and IPv6 filtered out)."

  value = try(
    [
      for ip in hyperv_machine_instance.this.network_adaptors[0].ip_addresses : ip
      if can(regex("^\\d+\\.\\d+\\.\\d+\\.\\d+$", ip)) && !startswith(ip, "169.254.")
    ][0],
    null
  )
}
