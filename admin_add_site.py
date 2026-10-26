545
546
547
548
549
550
551
552
553
554
555
556
557
558
559
560
561
562
563
564
565
566
567
568
569
570
571
572
573
574
575
576
577
578
579
580
581
582
583
584
585
586
587
588
589
590
591
592
593
594
595
596
597
598
599
600
601
602
603
604
605
606
607
608
609
610
611
612
613
614
615
616
617
618
619
620
621
622
623
624
625
626
627
628
629
630
631
632
633
634
635
636
637
638
639
640
641
642
643
644
645
646
647
648
649
650
651
652
653
654
655
656
657
658
659
660
661
662
663
664
665
666
                        x = st.number_input(f"{label} x", value=quad[i][0], key=f"admin_{label}_x")
                        y = st.number_input(f"{label} y", value=quad[i][1], key=f"admin_{label}_y")
                        new_quad.append((int(x), int(y)))
                st.session_state["admin_quad"] = new_quad
                quad = new_quad
        finally:
            if preview is not None:
                preview.close()
            gc.collect()

        st.divider()

        site_name = st.text_input(
            "Site filename (must match the naming convention, e.g. 'Geelong (Digital) - 32201-D.png')",
            value=st.session_state["admin_upload_name"] or "",
            key="admin_site_name",
        )

        save_clicked = st.button("Save Site", type="primary", width="stretch")

        if save_clicked:
            with st.spinner("Saving site…"):
                _handle_save(site_name, quad, working_path, template_dir, job_dir)

        _render_admin_errors()


def _render_admin_errors() -> None:
    for error in st.session_state.get("admin_errors", []):
        st.error(error)


def _render_password_gate() -> None:
    """
    The actual security boundary for this feature. The '+ Add Site' button
    itself stays visible to everyone — hiding a button client-side isn't
    real protection anyway. The real gate is here: no upload/detect/save/
    GitHub-commit code in the caller ever executes without a correct
    password, checked server-side in Python before anything else runs.

    On success, sets both the session flag (instant, this tab) and a
    24-hour signed URL token (survives reloads/new tabs within the window)
    before triggering a plain rerun — safe here since this isn't inside a
    dialog.
    """
    if not os.environ.get("ADMIN_PASSWORD"):
        st.error(
            "❌ Adding sites is locked, and ADMIN_PASSWORD isn't configured, so "
            "nobody can unlock it right now. Set ADMIN_PASSWORD in Render's "
            "environment variables (and export it locally for local testing) to "
            "enable access."
        )
        return

    st.markdown("**This area is password-protected.**")
    entered = st.text_input("Password", type="password", key="admin_password_input")

    if st.button("Unlock", key="admin_password_submit"):
        secret = os.environ["ADMIN_PASSWORD"]
        if _verify_password(entered):
            st.session_state["admin_authenticated"] = True
            expiry = time.time() + AUTH_TOKEN_DURATION_SECONDS
            st.query_params["admin_auth"] = _generate_auth_token(secret, expiry)
            st.rerun()
        else:
            st.session_state["admin_errors"].append("❌ Incorrect password.")

    _render_admin_errors()


def _handle_save(site_name: str, quad, working_path: Path, template_dir: Path, job_dir: Path) -> None:
    if not site_name.strip():
        st.session_state["admin_errors"].append("Please enter a site filename.")
        return

    if (template_dir / site_name).exists():
        st.session_state["admin_errors"].append(
            f"❌ '{site_name}' already exists in Templates/Digital/. Choose a different "
            f"filename, or delete/rename the existing template first if you meant to replace it."
        )
        return

    png_bytes = working_path.read_bytes()
    coords_payload = {"split_ratio": [1.0], "LHS": quad}

    # 1. Immediate, this-session availability: write locally + merge into
    #    the in-memory template list (TEMPLATE_COORDINATES was already
    #    imported at process start, so a disk write alone wouldn't show up
    #    in the running app without this).
    try:
        template_dir.mkdir(parents=True, exist_ok=True)
        (template_dir / site_name).write_bytes(png_bytes)
        st.session_state["custom_templates"][site_name] = coords_payload
    except Exception as e:
        st.session_state["admin_errors"].append(f"❌ Could not save template locally: {e}")
        return

    # 2. Durable persistence via GitHub — best-effort, never silent.
    if github_sync.is_configured():
        try:
            github_sync.commit_site(site_name, quad, png_bytes)
            st.success(
                f"✅ '{site_name}' is ready to use now, and committed to GitHub for future deploys."
            )
        except Exception as e:
            st.warning(
                f"⚠️ '{site_name}' is ready to use for this session, but the GitHub commit "
                f"failed: {e}\n\nPaste this into template_coordinates.py manually to persist it:"
            )
            st.code(github_sync.format_entry(site_name, quad), language="python")
    else:
        st.success(f"✅ '{site_name}' is ready to use for this session.")
        st.caption("GITHUB_TOKEN not set — paste this into template_coordinates.py to persist it:")
        st.code(github_sync.format_entry(site_name, quad), language="python")

    # Working files are already copied to template_dir / committed to GitHub;
    # the job-scoped tmp copy is no longer needed.
    _cleanup_admin_job_dir()
    st.session_state["admin_upload_bytes"] = None
    st.session_state["admin_upload_name"] = None
    gc.collect()
