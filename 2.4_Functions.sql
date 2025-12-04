USE TrelloDB;
DELIMITER //

DROP FUNCTION IF EXISTS FUNC_Calculate_Completion_Rate;

CREATE FUNCTION FUNC_Calculate_Completion_Rate(p_CardID INT) 
RETURNS DECIMAL(5,2)
READS SQL DATA
DETERMINISTIC
BEGIN
    DECLARE v_TotalItems INT DEFAULT 0;
    DECLARE v_CompletedItems INT DEFAULT 0;
    DECLARE v_IsItemDone BOOLEAN;
    DECLARE v_Finished INT DEFAULT 0;
    
    DECLARE cur_items CURSOR FOR 
        SELECT CI.IsCompleted 
        FROM Checklist_Item CI
        JOIN Checklist C ON CI.ChecklistID = C.ChecklistID
        WHERE C.CardID = p_CardID;
        
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_Finished = 1;

    IF NOT EXISTS (SELECT 1 FROM Card WHERE CardID = p_CardID) THEN
        RETURN 0.00;
    END IF;

    OPEN cur_items;

    get_items: LOOP
        FETCH cur_items INTO v_IsItemDone;
        IF v_Finished = 1 THEN LEAVE get_items; END IF;

        SET v_TotalItems = v_TotalItems + 1;
        IF v_IsItemDone = TRUE THEN
            SET v_CompletedItems = v_CompletedItems + 1;
        END IF;
    END LOOP get_items;

    CLOSE cur_items;

    IF v_TotalItems = 0 THEN RETURN 0.00;
    ELSE RETURN (v_CompletedItems / v_TotalItems) * 100;
    END IF;
END //

DROP FUNCTION IF EXISTS FUNC_Get_Card_Labels_String;

CREATE FUNCTION FUNC_Get_Card_Labels_String(p_CardID INT) 
RETURNS VARCHAR(255)
READS SQL DATA
DETERMINISTIC
BEGIN
    DECLARE v_LabelName VARCHAR(50);
    DECLARE v_ResultString VARCHAR(255) DEFAULT '';
    DECLARE v_Finished INT DEFAULT 0;

    DECLARE cur_labels CURSOR FOR 
        SELECT L.Name 
        FROM Label L
        JOIN Card_Label CL ON L.LabelID = CL.LabelID
        WHERE CL.CardID = p_CardID;

    DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_Finished = 1;

    OPEN cur_labels;

    get_labels: LOOP
        FETCH cur_labels INTO v_LabelName;
        IF v_Finished = 1 THEN LEAVE get_labels; END IF;

        IF v_ResultString != '' THEN
            SET v_ResultString = CONCAT(v_ResultString, ', ', v_LabelName);
        ELSE
            SET v_ResultString = v_LabelName;
        END IF;
    END LOOP get_labels;

    CLOSE cur_labels;

    RETURN v_ResultString;
END //

DELIMITER ;