_tls_ensure_private() {
        local f="$1"; shift
        [ -s "$f" ] || openssl genrsa -out "$f" 4096
    }
    _tls_san() {
        token = $(curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 3600")
    
        IPADDR=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/local-ipv4)
        LOCALDNS=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/local-hostname)
        {
            ip -oneline address | awk '{ gsub(/\/.+$/, "", $4); print "IP:" $4 }'
            {
                cat /etc/hostname
                echo 'docker'
                echo 'localhost'
                echo $LOCALDNS
                hostname -f
                hostname -s
                echo $IPADDR
            } | sed 's/^/DNS:/'
            [ -z "${DOCKER_TLS_SAN:-}" ] || echo "$DOCKER_TLS_SAN"
        } | sort -u | xargs printf '%s,' | sed "s/,\$//"
    }

    _tls_generate_certs() {
            local dir="$1"; shift
        
            # if ca/key.pem || !ca/cert.pem, generate CA public if necessary
            # if ca/key.pem, generate server public
            # if ca/key.pem, generate client public
            # (regenerating public certs every startup to account for SAN/IP changes and/or expiration)
        
            # https://github.com/FiloSottile/mkcert/issues/174
            local certValidDays='825'
        
            if [ -s "$dir/ca/key.pem" ] || [ ! -s "$dir/ca/cert.pem" ]; then
                # if we either have a CA private key or do *not* have a CA public key, then we should create/manage the CA
                mkdir -p "$dir/ca"
                _tls_ensure_private "$dir/ca/key.pem"
                openssl req -new -key "$dir/ca/key.pem" \
                    -out "$dir/ca/cert.pem" \
                    -subj '/CN=$HOSTNAME CA' -x509 -days "$certValidDays"
            fi
        
            if [ -s "$dir/ca/key.pem" ]; then
                # if we have a CA private key, we should create/manage a server key
                mkdir -p "$dir/server"
                _tls_ensure_private "$dir/server/key.pem"
                openssl req -new -key "$dir/server/key.pem" \
                    -out "$dir/server/csr.pem" \
                    -subj '/CN=docker:dind server'
                echo "[ x509_exts ]" >> $dir/server/openssl.cnf
                echo "subjectAltName = $(_tls_san)" >> $dir/server/openssl.cnf

                openssl x509 -req \
                        -in "$dir/server/csr.pem" \
                        -CA "$dir/ca/cert.pem" \
                        -CAkey "$dir/ca/key.pem" \
                        -CAcreateserial \
                        -out "$dir/server/cert.pem" \
                        -days "$certValidDays" \
                        -extfile "$dir/server/openssl.cnf" \
                        -extensions x509_exts
                cp "$dir/ca/cert.pem" "$dir/server/ca.pem"
                openssl verify -CAfile "$dir/server/ca.pem" "$dir/server/cert.pem"
            fi
        
            if [ -s "$dir/ca/key.pem" ]; then
                # if we have a CA private key, we should create/manage a client key
                mkdir -p "$dir/client"
                _tls_ensure_private "$dir/client/key.pem"
                chmod 0644 "$dir/client/key.pem" # openssl defaults to 0600 for the private key, but this one needs to be shared with arbitrary client contexts
                openssl req -new \
                        -key "$dir/client/key.pem" \
                        -out "$dir/client/csr.pem" \
                        -subj '/CN=docker:dind client'
                        
                echo "[ x509_exts ]" >> $dir/client/openssl.cnf
                echo "extendedKeyUsage = clientAuth" >> $dir/client/openssl.cnf
                
                openssl x509 -req \
                        -in "$dir/client/csr.pem" \
                        -CA "$dir/ca/cert.pem" \
                        -CAkey "$dir/ca/key.pem" \
                        -CAcreateserial \
                        -out "$dir/client/cert.pem" \
                        -days "$certValidDays" \
                        -extfile "$dir/client/openssl.cnf" \
                        -extensions x509_exts
                cp "$dir/ca/cert.pem" "$dir/client/ca.pem"
                openssl verify -CAfile "$dir/client/ca.pem" "$dir/client/cert.pem"
            fi
        }